"""Main module of AnnotSV"""

# std import
import logging

from pathlib import Path
from typing import Any, Dict, List, Optional

# 3rd party import
import typer


# Only official support 1/0 as CLI param, but check for more just in case
def to_bool(ctx: typer.Context, param: typer.CallbackParam, val):
    if val is None or isinstance(val, bool):
        return val
    return strtobool(val.strip().replace('"', ""))

logger = logging.getLogger(__name__)

typer_cli = typer.Typer(name="pyAnnotSV")

@typer_cli.command()
def annotsv(
    ctx: typer.Context,
    sv_input_file: Path = typer.Option(
        ...,
        "--SVinputFile",
        dir_okay=False,
        file_okay=True,
        help="Path of your VCF or BED input file with SV coordinates",
        metavar="INPUT_FILE",
        readable=True,
        resolve_path=True,
    ),
    snv_indel_files: Optional[str] = typer.Option(
        None,
        "--snvIndelFiles",
        help="Path of the VCF input file(s) with SNV/indel coordinates used for false positive discovery. Use counts of the homozygous and heterozygous variants. Gzipped VCF files are supported as well as regular expressions",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--outputDir",
        dir_okay=True,
        file_okay=False,
        resolve_path=True,
        writable=True,
        help="Output directory path, required unless --outputFile is also used",
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--outputFile",
        dir_okay=False,
        file_okay=True,
        writable=True,
        help="Output file path, required unless --outputDir is also used",
    ),
    annotations_dir: Optional[Path] = typer.Option(
        None,
        "--annotationsDir",
        dir_okay=True,
        file_okay=False,
        help="Path of the annotations directory",
        metavar="FILE",
        readable=True,
        resolve_path=True,
    ),
    annotation_mode: Optional[str] = typer.Option(
        None,
        case_sensitive=False,
        help="Selection of the type of annotation lines produced by AnnotSV",
    ),
    bcftools: Optional[Path] = typer.Option(
        None,
        "--bcftools",
        help="Path of the bcftools local installation",
    ),
    bedtools: Optional[Path] = typer.Option(
        None,
        "--bedtools",
        help="Path of the bedtools local installation",
    ),
    candidate_genes_file: Optional[Path] = typer.Option(
        None,
        "--candidateGenesFile",
        dir_okay=False,
        exists=True,
        file_okay=True,
        readable=True,
        resolve_path=True,
        help="Path of a file containing the candidate genes of the user (gene names can be space-separated, tabulation-separated, or line-break-separated) (optional)",
    ),
    candidate_genes_filtering: Optional[bool] = typer.Option(
        None,
        "--candidateGenesFiltering",
        is_flag=False,
        callback=to_bool,
        metavar="[0|1]",
        help="To select only the SV annotations ('split' and 'full') overlapping a gene from the 'candidateGenesFile'",
    ),
    candidate_snv_indel_files: Optional[str] = typer.Option(
        None,
        "--candidateSnvIndelFiles",
        help="Path of the filtered VCF input file(s) with SNV/indel coordinates for compound heterozygotes report (optional). Gzipped VCF files are supported as well as regular expression",
    ),
    candidate_snv_indel_samples: List[str] = typer.Option(
        [],
        "--candidateSnvIndelsamples",
        help="To specifiy the sample names from the VCF files defined from the -filtereVCFfiles option. Default: use all samples from the filtered VCF files",
    ),
    external_gene_files: List[Path] = typer.Option(
        [],
        "--externalGeneFiles",
        help="Path of tab separated values file(s) to integrate external gene annotations into the output file. The first line should be a header including a column entitled 'genes'. Gzipped files are supported",
    ),
    genome_build: str = typer.Option(
        None,
        "--genomeBuild",
        case_sensitive=False,
        help="Genome build used",
    ),
    hpo: Optional[str] = typer.Option(
        None,
        "--hpo",
        help="HPO terms list describing the phenotype of the individual being investigated. Values: use comma, semicolon or space separated class values (e.g.: 'HP:0001156,HP:0001363,HP:0011304')",
    ),
    include_ci: Optional[bool] = typer.Option(
        None,
        "--includeCI",
        callback=to_bool,
        is_flag=False,
        metavar="[0|1]",
        help="To expand the 'start' and 'end' SV positions with the VCF confidence intervals (CIPOS, CIEND) around the breakpoints",
    ),
    metrics: str = typer.Option(
        None,
        "--metrics",
        case_sensitive=False,
        help="Changing numerical values from frequencies to us or fr metrics (e.g. 0.2 or 0,2)",
    ),
    min_total_number: int = typer.Option(
        500,
        "--minTotalNumber",
        min=100,
        max=1000,
        metavar="[100, 1000]",
        help="Minimum number of individuals tested to consider a benign SV for the ranking",
    ),
    overlap: int = typer.Option(
        100,
        "--overlap",
        min=0,
        max=100,
        metavar="[0, 100]",
        help="Minimum overlap (%) between the user features and the annotated SV to be reported",
    ),
    overwrite: Optional[bool] = typer.Option(
        None,
        "--overwrite",
        callback=to_bool,
        is_flag=False,
        metavar="[0|1]",
        help="To overwrite existing output results",
    ),
    promoter_size: int = typer.Option(
        500,
        "--promoterSize",
        min=1,
        metavar="[1, inf)",
        help="Number of bases upstream from the transcription start site",
    ),
    rank_filtering: str = typer.Option(
        "1-5,NA",
        "--rankFiltering",
        help="To select the SV of an user-defined specific class (from 1 to 5). Values: use comma separated class values, or use a dash to denote a range of values ( e.g.: '3,4,5' or '3-5')",
    ),
    reciprocal: Optional[bool] = typer.Option(
        None,
        "--reciprocal",
        callback=to_bool,
        is_flag=False,
        metavar="[0|1]",
        help="Use of a reciprocal overlap between SV and user features (only for annotations with features overlapping the SV)",
    ),
    re_report: Optional[bool] = typer.Option(
        None,
        "--REreport",
        callback=to_bool,
        is_flag=False,
        metavar="[0|1]",
        help="Create a report to link the annotated SV and the overlapped regulatory elements (coordinates and sources)",
    ),
    samplesid_bed_col: Optional[int] = typer.Option(
        None,
        "--samplesidBEDcol",
        min=4,
        metavar="[4, inf)",
        help="Number of the column reporting the samples ID for which the SV was called (if the input SV file is a BED). (Samples ID should be comma or space separated)",
    ),
    snvindel_pass: bool = typer.Option(
        False,
        "--snvindelPASS",
        callback=to_bool,
        metavar="[0|1]",
        help="Only use variants from VCF input files that passed all filters during the calling (FILTER column value equal to PASS)",
    ),
    snv_indel_samples: Optional[str] = typer.Option(
        None,
        "--snvIndelSamples",
        help="To specifiy the sample names from the VCF files defined from the -vcfFiles option. Default: use all samples from the VCF files",
    ),
    sv_input_info: bool = typer.Option(
        True,
        "--SVinputInfo",
        callback=to_bool,
        metavar="[0|1]",
        help="Extract additional SV input fields and insert the data into the output file",
    ),
    sv_min_size: int = typer.Option(
        50,
        "--SVminSize",
        min=1,
        metavar="[1, inf)",
        help="SV minimum size (in bp)",
    ),
    svt_bed_col: Optional[int] = typer.Option(
        None,
        "--svtBEDcol",
        min=4,
        metavar="[4, inf)",
        help="Number of the column describing the SV type (DEL, DUP) if the input SV file is a BED",
    ),
    tx: str = typer.Option(
        None,
        "--tx",
        case_sensitive=False,
        help="Origin of the transcripts",
    ),
    tx_file: Optional[Path] = typer.Option(
        None,
        "--txFile",
        dir_okay=False,
        exists=True,
        file_okay=True,
        readable=True,
        resolve_path=True,
        help="Path of a file containing a list of preferred genes transcripts to be used in priority during the annotation. (Preferred genes transcripts names should be tab or space separated)",
    ),
):
    params: Dict[str, Any] = {to_camel(k): v for k, v in ctx.params.items() if v is not None}

    print(params)


typer_cli()
