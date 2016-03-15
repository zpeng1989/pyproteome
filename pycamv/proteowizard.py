"""
Provides functions for interacting with MS data through ProteoWizard.
"""

import os
import platform
import re
import requests
import shutil
import subprocess
import tempfile

import pymzml

from pyproteome import paths


THIS_DIR = os.path.abspath(os.path.dirname(__file__))
PROTEOWIZARD_DIR = os.path.join(THIS_DIR, "ProteoWizard")

PROTEOWIZARD_VERSION = "3.0.9393"
PROTEOWIZARD_PATH = os.path.join(
    PROTEOWIZARD_DIR,
    "ProteoWizard {}".format(PROTEOWIZARD_VERSION),
)

PROTEOWIZARD_MSI_32_URL = (
    "https://www.dropbox.com/s/5q7flvb32vgdh7d/"
    "pwiz-setup-3.0.9393-x86.msi?dl=0"
)

PROTEOWIZARD_MSI_64_URL = (
    "https://www.dropbox.com/s/7bz3wpgjj7zd99a/"
    "pwiz-setup-3.0.9393-x86_64.msi?dl=0"
)


class ScanQuery:
    """
    Attributes
    ----------
    scan : int
    isolation_mz : float or None
    precursor_scan : int or None
    """
    def __init__(self, scan, isolation_mz=None, precursor_scan=None):
        self.scan = scan
        self.precursor_scan = precursor_scan
        self.isolation_mz = isolation_mz


def fetch_proteowizard(url=None):
    if os.file.exists(PROTEOWIZARD_PATH):
        return

    if platform.sytem() not in ["Windows"]:
        raise Exception("Proteowizard install not supported on your platform")

    if url is None:
        if platform.architecture()[0] == "64bit":
            url = PROTEOWIZARD_MSI_64_URL
        else:
            url = PROTEOWIZARD_MSI_32_URL

    tmpdir = tempfile.mkdtemp()

    # Download and extract the install .msi file
    with open(tempfile.NamedTemporaryFile(mode="w+b", suffix=".msi")) as f:
        response = requests.get(url, stream=True)

        if not response.ok:
            raise Exception("Unable to download file: {}".format(response))

        for block in response.iter_content(1024):
            f.write(block)

        f.flush()

        cmd = [
            "msiexec",
            "/a",
            f.name,
            "/qb",
            "TARGETDIR=\"{}\"".format(tmpdir),
        ]
        subprocess.check_call(cmd)

    # Copy the msi file's contents to PROTEOWIZARD_DIR
    src = os.path.join(
        tmpdir,
        "PFiles",
        "ProteoWizard",
    )

    os.makedirs(PROTEOWIZARD_DIR)
    shutil.copytree(src, PROTEOWIZARD_DIR)
    shutil.rmtree(tmpdir)


def _raw_to_mzml(basename, queries, out_dir, mz_window=None):
    """
    Parameters
    ----------
    basename : str
    queries : list of :class:`PeptideQuery<pycamv.mascot.PeptideQuery>`
    out_dir : str
    mz_window : list of int, optional
    """
    ms_convert_path = os.path.join(PROTEOWIZARD_PATH, "msconvert.exe")
    raw_path = os.path.join(paths.MS_RAW_DIR, "{}.raw".format(basename))

    # Create a config file,
    config = tempfile.NamedTemporaryFile(mode="w+", suffix=".txt")

    config.write(
        "filter=\"scanNumber {}\"\n".format(
            " ".join(str(query.scan) for query in queries)
        )
    )

    if mz_window:
        config.write(
            "filter=\"mzWindow [{},{}]\"\n".format(
                mz_window[0], mz_window[1],
            )
        )

    config.flush()

    cmd = [
        ms_convert_path,
        raw_path,
        "-o", out_dir,
        "--mzML",
        "-c", config.name,
    ]

    subprocess.check_call(cmd)
    config.close()

    out_path = os.path.join(out_dir, "{}.mzML".format(basename))
    data = pymzml.run.Reader(
        out_path,
    )

    return data


def get_scan_data(basename, queries):
    """
    Gets MS^2 and MS data for all scans in queries.

    Parameters
    ----------
    basename : str
    queries : list of :class:`PeptideQuery<pycamv.mascot.PeptideQuery>`

    Returns
    -------
    list of :class:`ScanQuery<pycamv.proteowizard.ScanQuery>`
    """
    out_dir = tempfile.mkdtemp()

    # Collect MS^2 data
    ms2_data = _raw_to_mzml(basename, queries, out_dir)

    prefix = {"mzml": "http://psi.hupo.org/ms/mzml"}
    scan_queries = []

    for spectrum in ms2_data:
        if spectrum["ms level"] != 2:
            continue

        scan = spectrum["id"]
        isolation_mz = spectrum["selected ion m/z"]

        spectrum_ref = spectrum.xmlTreeIterFree.find(
            "mzml:precursorList/mzml:precursor", prefix,
        ).get("spectrumRef")
        precursor_scan = re.search("scan=(\d+)", spectrum_ref).group(1)

        scan_queries.append(
            ScanQuery(
                scan,
                precursor_scan=precursor_scan,
                isolation_mz=isolation_mz,
            )
        )

    # Collect MS^1 data
    ms_data = _raw_to_mzml(
        basename,
        sorted(set(i.precursor_scan for i in scan_queries)),
        out_dir,
    )

    # del ms2_data
    # shutil.rmtree(out_dir)

    return scan_queries, spectrum