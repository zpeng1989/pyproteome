"""
This module provides functionality for accessing searched data from Proteome
Discoverer.
"""

from collections import defaultdict
import logging
import os
import re
import sqlite3
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from . import loading, modification, paths, protein


LOGGER = logging.getLogger("pyproteome.discoverer")
RE_ACCESSION = re.compile(r"^>sp\|([\dA-Za-z]+)\|[\dA-Za-z_]+ .*$")
RE_DESCRIPTION = re.compile(r"^>sp\|[\dA-Za-z]+\|[\dA-Za-z_]+ (.*)$")


def _read_peptides(conn):
    df = pd.read_sql_query(
        """
        SELECT
        Peptides.PeptideID,
        Peptides.SpectrumID,
        Peptides.Sequence,
        Peptides.ConfidenceLevel AS "Confidence Level",
        PeptideScores.ScoreValue AS "IonScore",
        SpectrumHeaders.FirstScan AS "First Scan",
        SpectrumHeaders.LastScan AS "Last Scan",
        FileInfos.FileName AS "Spectrum File"
        FROM
        Peptides JOIN
        PeptideScores JOIN
        SpectrumHeaders JOIN
        FileInfos JOIN
        Masspeaks
        WHERE
        Peptides.PeptideID=PeptideScores.PeptideID AND
        Peptides.SpectrumID=SpectrumHeaders.SpectrumID AND
        FileInfos.FileID=MassPeaks.FileID AND
        Masspeaks.MassPeakID=SpectrumHeaders.MassPeakID
        """,
        conn,
    )

    df.index = df["PeptideID"]
    del df["PeptideID"]

    return df


def _extract_sequence(df):
    df["Sequence"] = df.apply(
        lambda row:
        loading.extract_sequence(
            row["Proteins"],
            row["Sequence"],
        ),
        axis=1,
    )

    return df


def _get_proteins(df, cursor):
    prots = cursor.execute(
        """
        SELECT
        Peptides.PeptideID,
        ProteinAnnotations.Description
        FROM
        Peptides JOIN
        PeptidesProteins JOIN
        ProteinAnnotations
        WHERE
        Peptides.PeptideID=PeptidesProteins.PeptideID AND
        ProteinAnnotations.ProteinID=PeptidesProteins.ProteinID
        """,
    )

    accessions = defaultdict(list)
    descriptions = defaultdict(list)

    for protein_id, prot_string in prots:
        accessions[protein_id].append(
            RE_ACCESSION.match(prot_string).group(1)
        )

        descriptions[protein_id].append(
            RE_DESCRIPTION.match(prot_string).group(1)
        )

    # fetch_data.fetch_uniprot_data(
    #     [
    #         accession
    #         for lst in accessions.values()
    #         for accession in lst
    #     ]
    # )

    df["Protein Descriptions"] = df.index.map(
        lambda peptide_id:
        "; ".join(descriptions[peptide_id])
    )

    df["Protein Group Accessions"] = df.index.map(
        lambda peptide_id:
        "; ".join(accessions[peptide_id])
    )

    df["Proteins"] = df.index.map(
        lambda peptide_id:
        protein.Proteins(
            proteins=[
                protein.Protein(
                    accession=accession,
                )
                for accession in accessions[peptide_id]
            ]
        )
    )

    return df


def _get_modifications(df, cursor):
    aa_mods = cursor.execute(
        """
        SELECT
        Peptides.PeptideID,
        AminoAcidModifications.Abbreviation,
        PeptidesAminoAcidModifications.Position
        FROM
        Peptides JOIN
        PeptidesAminoAcidModifications JOIN
        AminoAcidModifications
        WHERE
        Peptides.PeptideID=PeptidesAminoAcidModifications.PeptideID AND
        PeptidesAminoAcidModifications.AminoAcidModificationID=
        AminoAcidModifications.AminoAcidModificationID
        """,
    )

    aa_mod_dict = defaultdict(list)

    for peptide_id, name, pos in aa_mods:
        sequence = df.loc[peptide_id]["Sequence"]

        mod = modification.Modification(
            rel_pos=pos,
            mod_type=name,
            nterm=False,
            cterm=False,
            sequence=sequence,
        )

        aa_mod_dict[peptide_id].append(mod)

    term_mods = cursor.execute(
        """
        SELECT
        Peptides.PeptideID,
        AminoAcidModifications.Abbreviation,
        AminoAcidModifications.PositionType
        FROM
        Peptides JOIN
        PeptidesTerminalModifications JOIN
        AminoAcidModifications
        WHERE
        Peptides.PeptideID=PeptidesTerminalModifications.PeptideID AND
        PeptidesTerminalModifications.TerminalModificationID=
        AminoAcidModifications.AminoAcidModificationID
        """,
    )

    term_mod_dict = defaultdict(list)

    # PositionType rules taken from:
    #
    # https://github.com/compomics/thermo-msf-parser/blob/
    # 697a2fe94de2e960a9bb962d1f263dc983461999/thermo_msf_parser_API/
    # src/main/java/com/compomics/thermo_msf_parser_API/highmeminstance/
    # Parser.java#L1022
    for peptide_id, name, pos_type in term_mods:
        nterm = pos_type == 1
        mod = modification.Modification(
            rel_pos=pos,
            mod_type=name,
            nterm=nterm,
            cterm=not nterm,
            sequence=sequence,
        )
        term_mod_dict[peptide_id].append(mod)

    df["Modifications"] = df.index.map(
        lambda peptide_id:
        modification.Modifications(
            mods=(
                term_mod_dict[peptide_id] +
                aa_mod_dict[peptide_id]
            ),
        )
    )

    return df


def _get_quantifications(df, cursor, tag_names):
    # XXX: Bug: Peak heights do not exactly match those from Discoverer
    # for name in tag_names:
    #     df[name] = np.nan

    vals = cursor.execute(
        """
        SELECT
        Peptides.PeptideID,
        ReporterIonQuanResults.QuanChannelID,
        ReporterIonQuanResults.Height
        FROM
        Peptides JOIN
        ReporterIonQuanResults JOIN
        ReporterIonQuanResultsSearchSpectra
        WHERE
        Peptides.SpectrumID=
        ReporterIonQuanResultsSearchSpectra.SearchSpectrumID AND
        ReporterIonQuanResultsSearchSpectra.SpectrumID=
        ReporterIonQuanResults.SpectrumID
        """,
    )

    mapping = {
        (peptide_id, channel_id): height
        for peptide_id, channel_id, height in vals
    }

    channel_ids = sorted(set(i[1] for i in mapping.keys()))

    for channel_id in channel_ids:
        tag_name = tag_names[channel_id - 1]
        df[tag_name] = df.index.map(
            lambda peptide_id:
            mapping.get((peptide_id, channel_id), np.nan)
        )

    return df


def read_discoverer_msf(basename):
    """
    Read a Proteome Discoverer .msf file.

    Converts file contents into a pandas DataFrame similar to what one would
    get by exporting peptides to .txt directly from Discoverer.

    Parameters
    ----------
    path : str

    Returns
    -------
    :class:`pandas.DataFrame`
    """
    msf_path = os.path.join(
        paths.MS_SEARCHED_DIR,
        basename + ".msf",
    )

    LOGGER.info(
        "Loading MASCOT peptides from \"{}\"".format(
            os.path.basename(msf_path),
        )
    )

    with sqlite3.connect(msf_path) as conn:
        cursor = conn.cursor()

        # Get any N-terminal quantification tags
        quantification = cursor.execute(
            """
            SELECT
            ParameterValue
            FROM ProcessingNodeParameters
            WHERE ProcessingNodeParameters.ParameterName="QuantificationMethod"
            """,
        ).fetchone()

        if quantification:
            root = ET.fromstring(quantification[0])
            quant_tags = root.findall(
                "MethodPart/MethodPart/Parameter[@name='TagName']",
            )
            tag_names = [i.text for i in quant_tags]
        else:
            tag_names = None

        # Read the main peptide properties
        df = _read_peptides(conn)

        df = _get_proteins(df, cursor)

        df = _extract_sequence(df)

        # 1 -> "Low", 2 -> "Medium", 3 -> "High"
        confidence_mapping = {1: "Low", 2: "Medium", 3: "High"}
        df["Confidence Level"] = df["Confidence Level"].apply(
            lambda x: confidence_mapping[x]
        )

        # "path/to/file.ext" => "file.ext"
        df["Spectrum File"] = df["Spectrum File"].apply(
            lambda x: os.path.split(x)[1]
        )

        df = _get_modifications(df, cursor)

        for _, row in df.iterrows():
            row["Sequence"].modifications = row["Modifications"]

        if tag_names:
            df = _get_quantifications(df, cursor, tag_names)

    df.reset_index(inplace=True, drop=True)

    return df
