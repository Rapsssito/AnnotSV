# -*- coding: utf-8 -*-

from __future__ import division
from __future__ import print_function

import logging as log
import os
import pandas as pd
import sys
import time
from natsort import index_natsorted

from converters.abstract_converter import AbstractConverter

sys.path.append("..")
from commons import create_vcf_header, is_helper_func, remove_decimal_or_strip
from helper_functions import HelperFunctions


class VcfFromAnnotsv(AbstractConverter):
    """
    Specificities compared to TSV:
    - vcf-like INFO field  in addition to other annotation columns
    - vcf-like FORMAT and <sample> fields
    - full/split annotations. Each variant can have one "full" and
    zero to many "split" annotations which result in additional lines in the file
    Very hard to deal with this with generic code --> it gets its own converter

    Sept 2022 update: add support for AnnotSV files obtained from bed files
    Those do not have REF, ALT, FORMAT and <sample_name> columns
    """

    def _build_input_dataframe(self):
        df = pd.read_csv(
            self.filepath,
            skiprows=self.config["GENERAL"]["skip_rows"],
            sep="\t",
            low_memory=False,
        )
        df.sort_values(
            [self.config["VCF_COLUMNS"]["#CHROM"], self.config["VCF_COLUMNS"]["POS"]],
            inplace=True,
        )
        df.reset_index(drop=True, inplace=True)
        df.fillna(".", inplace=True)
        df = df.astype(str)
        log.debug(df)
        return df

    def _get_sample_list(self):
        samples_col = self.input_df[self.config["VCF_COLUMNS"]["SAMPLE"]]
        sample_list = []
        for cell in samples_col:
            if "," in cell:
                for sample in cell.split(","):
                    sample_list.append(sample)
            else:
                sample_list.append(cell)
        # print(samples_col)
        sample_list = list(set(sample_list))
        # print("sample_list:", sample_list)
        if self.config["VCF_COLUMNS"]["FORMAT"] == "FORMAT":
            if not set(sample_list).issubset(self.input_df.columns):
                raise ValueError(
                    "When using an AnnotSV file generated from a VCF, all samples in '"
                    + samples_col
                    + "' column are expected to "
                    "have their own column in the input AnnotSV file"
                )
        return sample_list

    def _build_input_annot_df(self):
        """
        remove FORMAT, Samples_ID, and each <sample> column
        TODO: remove vcf base cols ; INFO field
        """
        columns_to_drop = [v for v in self.sample_list]
        columns_to_drop += [v for v in self.main_vcf_cols]
        columns_to_drop.append(self.config["VCF_COLUMNS"]["SAMPLE"])
        columns_to_drop.append(self.config["VCF_COLUMNS"]["FORMAT"])
        columns_to_drop.append(self.config["VCF_COLUMNS"]["INFO"]["INFO"])
        for col in columns_to_drop:
            try:
                df = self.input_df.drop([col], axis=1)
            except KeyError:
                log.debug(f"Failed to drop column: {col}")
        df = df.replace(";", ",", regex=True)  # any ';' in annots will ruin the vcf INFO field

        # TODO: check if CHROM col is in compliance with config ref genome (chrX or X)
        # if self.config["GENOME"]["vcf_header"][0].startswith("##contig=<ID=chr"):
        #     if not chrom.startswith

        if (
            self.config["VCF_COLUMNS"]["INFO"]["SV_type"] == ""
            or self.config["VCF_COLUMNS"]["INFO"]["SV_type"] not in df.columns
        ):
            raise ValueError(
                "SV_type column is required to turn an AnnotSV file into a VCF. Check if SV_type col is set in config or missing in your file.\n"
                + "If you generated your AnnotSV file from a bed, AnnotSV option -svtBEDcol is required."
            )
        return df

    def _merge_full_and_split(self, df):
        """
        input: df of a single annotSV_ID ; containing only annotations (no sample/FORMAT data)
        it can contain full and/or split annotations

        returns a single line dataframe with all annotations merged properly
        """
        if self.config["GENERAL"]["mode"] != "full&split":
            raise ValueError(
                "Unexpected value in json config['GENERAL']['mode']: "
                "only 'full&split' mode is implemented yet."
            )
        # Do not keep 'base vcf col' in info field
        df = df.loc[
            :,
            [cols for cols in df.columns if cols not in ["ID", "REF", "ALT", "QUAL", "FILTER"]],
        ]

        annots = {}
        dfs = {}
        for typemode, df_type in df.groupby(self.config["VCF_COLUMNS"]["INFO"]["Annotation_mode"]):
            if typemode not in ("full", "split"):
                raise ValueError("Annotation type is assumed to be only 'full' or 'split'")
            dfs[typemode] = df_type

        # deal with full
        if "full" not in dfs.keys():
            # still need to init columns
            if "split" not in dfs.keys():
                log.warning(
                    "Input does not include AnnotSV's 'Annotation_mode' column. This is necessary to know how to deal with annotations. The INFO field will be empty."
                )
                return {}
            for ann in dfs["split"].columns:
                annots[ann] = "."
        else:
            if len(dfs["full"].index) > 1:
                raise ValueError(
                    "Each variant is assumed to only have one single line of 'full' annotation"
                )
            # remove float decimal full rows
            for ann in dfs["full"].columns:
                annots[ann] = remove_decimal_or_strip(dfs["full"].loc[df.index[0], ann])

        # deal with split
        if "split" not in dfs.keys():
            return annots
        # each info field split
        for ann in dfs["split"].columns:
            transform = []
            if ann == self.config["VCF_COLUMNS"]["INFO"]["Annotation_mode"]:
                annots[ann] = self.config["GENERAL"]["mode"]
                continue
            # if you only keep full annotations split is lost advitam eternam
            # list of all values in each columns
            for splitval in dfs["split"][ann].tolist():
                transform.append(remove_decimal_or_strip(splitval))
            # we don't report split infos only if there are ALL equal to full row or they are stack to dot
            # if all([nq == annots[ann] for nq in transform]) or all(
            #     eq == "." for eq in transform
            # ):  # or ann in except_full_list:

            #    continue
            # In case of full and n split are different we keep values from all (more than 2 differencies)
            # else:
            values = [annots[ann]]
            values.extend(transform)
            annots[ann] = "|".join(values)
            # TODO in case of pipe already present in annotations change separator, maybe '+'

        # remove empty annots
        annots = {k: v for k, v in annots.items()}
        return annots

    def _build_info_dic(self):
        """
        Output: dictionary with key: annotsv_ID ; value: a key-value dictionary of all annotations
        This will be used to write the INFO field
        """
        input_annot_df = self._build_input_annot_df()
        # print(input_annot_df)
        annots_dic = {}
        id_col = self.config["VCF_COLUMNS"]["INFO"]["AnnotSV_ID"]
        for variant_id, df_variant in input_annot_df.groupby(id_col):
            merged_annots = self._merge_full_and_split(df_variant)
            annots_dic[variant_id] = merged_annots
        # print(annots_dic)
        return annots_dic

    # TODO: merge this with the other create_vcf_header method if possible
    # Making this method static is an attempt at making it possible to kick it out of the class
    @staticmethod
    def _create_vcf_header(input_path, config, sample_list, input_df, info_keys):
        header = []
        header.append("##fileformat=VCFv4.2")
        header.append("##fileDate=%s" % time.strftime("%d/%m/%Y"))
        header.append("##source=" + config["GENERAL"]["origin"])
        header.append("##InputFile=%s" % os.path.abspath(input_path))

        if config["VCF_COLUMNS"]["FILTER"] in input_df.columns:
            for filter in set(input_df[config["VCF_COLUMNS"]["FILTER"]].to_list()):
                header.append("##FILTER=<ID=" + str(filter) + ',Description=".">')
        else:
            header.append('##FILTER=<ID=PASS,Description="Passed filter">')

        # identify existing values in header_dic...
        header_dic = {}
        header_dic["REF"] = set(input_df[config["VCF_COLUMNS"]["REF"]].to_list())
        header_dic["ALT"] = set(input_df[config["VCF_COLUMNS"]["ALT"]].to_list())
        # ... then for each of them, check if a description was given in the config
        for section in header_dic:
            for key in header_dic[section]:
                if key in config["COLUMNS_DESCRIPTION"][section]:
                    info_config = config["COLUMNS_DESCRIPTION"][section][key]
                    header.append(
                        "##"
                        + section
                        + "=<ID="
                        + key
                        + ',Description="'
                        + info_config["Description"]
                        + '">'
                    )
                else:
                    header.append(
                        "##"
                        + section
                        + "=<ID="
                        + key
                        + ',Description="Imported from '
                        + config["GENERAL"]["origin"]
                        + '">'
                    )

        # same as before, but for header elements that also have a type...
        header_dic = {}
        header_dic["INFO"] = info_keys
        header_dic["FORMAT"] = set()
        for format_field in input_df[config["VCF_COLUMNS"]["FORMAT"]].to_list():
            for format in format_field.split(":"):
                header_dic["FORMAT"].add(format)
        # ... then for each of them, check if a description was given in the config
        for section in header_dic:
            for key in header_dic[section]:
                if key in config["COLUMNS_DESCRIPTION"][section]:
                    info_config = config["COLUMNS_DESCRIPTION"][section][key]
                    header.append(
                        "##"
                        + section
                        + "=<ID="
                        + key
                        + ",Number=.,Type="
                        + info_config["Type"]
                        + ',Description="'
                        + info_config["Description"]
                        + '">'
                    )
                else:
                    header.append(
                        "##"
                        + section
                        + "=<ID="
                        + key
                        + ',Number=.,Type=String,Description="Imported from '
                        + config["GENERAL"]["origin"]
                        + '">'
                    )

        header += config["GENOME"]["vcf_header"]
        header.append(
            "\t".join(
                [
                    "#CHROM",
                    "POS",
                    "ID",
                    "REF",
                    "ALT",
                    "QUAL",
                    "FILTER",
                    "INFO",
                    "FORMAT",
                ]
                + sample_list
            )
        )
        return header

    def _get_main_vcf_cols(self):
        cols = []
        for col in ["#CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER"]:
            config_col = self.config["VCF_COLUMNS"][col]
            if not isinstance(config_col, str):
                self.input_df[col] = "."
            elif config_col == "":
                self.input_df[col] = "."
            else:
                col = config_col
            cols.append(col)
        print("main_cols:", cols)
        return cols

    def convert(self, tsv, output_path):
        """
        Creates and fill the output file.

        For each annotSV_ID ; fetch all related lines of annotations in key value dics.
        A function identifies and merges the annotations.
        then we build a dictionary with 1 dictionary per annotSV_ID containing all the annotations
        This is then used to make the header and fill the INFO field.

        Note: the "INFO" field from annotSV is discarded for now,
        because it only contains Decon annotations and they're useless.
        TODO: make an option to keep the "INFO" field in the annotations dictionary
        """
        log.info("Converting to vcf from tsv using config: " + self.config_filepath)

        self.filepath = tsv
        helper = HelperFunctions(self.config)

        self.input_df = self._build_input_dataframe()
        self.sample_list = self._get_sample_list()
        self.main_vcf_cols = self._get_main_vcf_cols()

        info_dic = self._build_info_dic()
        info_keys = set()
        for id, dic in info_dic.items():
            for k in dic:
                info_keys.add(k)

        # create the vcf
        with open(output_path, "w") as vcf:
            vcf_header = create_vcf_header(tsv, self.config, self.sample_list)
            for l in vcf_header:
                vcf.write(l + "\n")

            id_col = self.config["VCF_COLUMNS"]["INFO"]["AnnotSV_ID"]
            self.input_df = self.input_df.iloc[
                index_natsorted(self.input_df[self.config["VCF_COLUMNS"]["#CHROM"]])
            ]

            for variant_id, df_variant in self.input_df.groupby(id_col, sort=False):

                # fill columns that need a helper func
                for config_key, config_val in self.config["VCF_COLUMNS"].items():
                    if config_key == "INFO":
                        for info_col in self.config["VCF_COLUMNS"][config_key].values():
                            if is_helper_func(info_col):
                                raise ValueError(
                                    "HELPER_FUNCTIONS for INFO fields are not implemented yet for AnnotSV converter"
                                )
                    elif config_key == "FILTER" and config_val == "":
                        df_variant[config_key] = "PASS"
                    elif is_helper_func(config_val):
                        func = helper.get(config_val[1])
                        args = [df_variant.iloc[0][c] for c in config_val[2:]]
                        result = func(*args)
                        df_variant[config_key] = result

                main_cols = "\t".join(df_variant[self.main_vcf_cols].iloc[0].to_list())
                vcf.write(main_cols + "\t")
                vcf.write(";".join([k + "=" + v for k, v in info_dic[variant_id].items()]) + "\t")

                if self.config["VCF_COLUMNS"]["FORMAT"] != "":
                    sample_cols = "\t".join(
                        df_variant[[self.config["VCF_COLUMNS"]["FORMAT"]] + self.sample_list]
                        .iloc[0]
                        .to_list()
                    )
                else:
                    sample_cols = "GT\t" + self.config["GENERAL"]["default_genotype"]
                vcf.write(sample_cols)
                vcf.write("\n")
