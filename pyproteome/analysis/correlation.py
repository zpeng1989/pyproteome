# -*- coding: UTF-8 -*-
"""
This module provides functionality for data set analysis.

Functions include volcano plots, sorted tables, and plotting sequence levels.
"""

from __future__ import division

# Built-ins
import logging
import os

# Core data analysis libraries
from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

# Misc extras
from adjustText.adjustText import adjust_text

import pyproteome
from . import utils


LOGGER = logging.getLogger("pyproteome.correlation")


def correlate_data_sets(
    data1, data2, folder_name=None, filename=None,
    adjust=True, label_cutoff=1.5,
):
    """
    Plot the correlation between peptides levels in two different data sets.

    Parameters
    ----------
    data1 : :class:`DataSet<pyproteome.data_sets.DataSet>`
    data2 : :class:`DataSet<pyproteome.data_sets.DataSet>`
    folder_name : str, optional
    filename : str, optional
    """
    if not folder_name:
        folder_name = "All" if data1.name != data2.name else data1.name

    utils.make_folder(folder_name)

    if folder_name and filename:
        filename = os.path.join(folder_name, filename)

    merged = pd.merge(
        data1.psms, data2.psms,
        on="Sequence",
    ).dropna(subset=("Fold Change_x", "Fold Change_y"))

    f, ax = plt.subplots()
    ax.scatter(
        np.log2(merged["Fold Change_x"]),
        np.log2(merged["Fold Change_y"]),
    )

    label_cutoff = np.log2(label_cutoff)
    texts, x_s, y_s = [], [], []

    for index, row in merged.iterrows():
        x = row["Fold Change_x"]
        y = row["Fold Change_y"]
        ratio = np.log2(x / y)
        x, y = np.log2(x), np.log2(y)

        if ratio < label_cutoff and ratio > - label_cutoff:
            continue

        x_s.append(x)
        y_s.append(y)

        txt = " / ".join(row["Proteins_x"].genes)
        txt = txt[:20] + ("..." if len(txt) > 20 else "")

        text = ax.text(
            x, y, txt,
        )

        text.set_bbox(
            dict(
                color="lightgreen" if ratio < 0 else "pink",
                alpha=0.8,
            )
        )
        texts.append(text)

    if adjust:
        adjust_text(
            x=x_s,
            y=y_s,
            texts=texts,
            ax=ax,
            lim=400,
            force_text=0.1,
            force_points=0.1,
            arrowprops=dict(arrowstyle="->", relpos=(0, 0), lw=1),
            only_move={
                "points": "y",
                "text": "xy",
            }
        )

    min_x = min(np.log2(merged["Fold Change_x"]))
    max_x = max(np.log2(merged["Fold Change_x"]))
    ax.plot([min_x, max_x], [min_x, max_x], "--")
    ax.plot(
        [min_x, max_x],
        [min_x + label_cutoff, max_x + label_cutoff],
        color="lightgreen",
        linestyle=":",
    )
    ax.plot(
        [min_x, max_x],
        [min_x - label_cutoff, max_x - label_cutoff],
        color="pink",
        linestyle=":",
    )

    name1 = data1.name
    name2 = data2.name

    ax.set_xlabel("$log_2$ Fold Change -- {}".format(name1))
    ax.set_ylabel("$log_2$ Fold Change -- {}".format(name2))

    pear_corr = pearsonr(merged["Fold Change_x"], merged["Fold Change_y"])
    spear_corr = spearmanr(merged["Fold Change_x"], merged["Fold Change_y"])

    ax.set_title(
        (
            r"Pearson's: $\rho$={:.2f}, "
            r"Spearman's: $\rho$={:.2f}"
        ).format(pear_corr[0], spear_corr[0])
    )

    if filename:
        f.savefig(
            filename,
            transparent=True,
            dpi=pyproteome.DEFAULT_DPI,
        )


def _spearmanr_nan(a, b, min_length=5):
    mask = ~np.array(
        [np.isnan(i) or np.isnan(j) for i, j in zip(a, b)],
        dtype=bool,
    )

    if mask.sum() < min_length:
        return spearmanr(np.nan, np.nan)

    return spearmanr(a[mask], b[mask])


def correlate_signal(
    data, signal,
    p=0.05,
    options=None,
    folder_name=None, title=None,
    scatter_colors=None,
    scatter_symbols=None,
    figsize=(12, 10),
    xlabel="",
):

    options = options or {}

    highlight = options.get('highlight', {})
    hide = options.get('hide', {})
    edgecolors = options.get('edgecolors', {})
    rename = options.get('rename', {})
    scatter_colors = options.get('scatter_colors', {})
    scatter_symbols = options.get('scatter_symbols', {})

    if title is None:
        title = data.name

    cp = data.copy()

    signal_groups = [
        label
        for label, group in cp.groups.items()
        for chan in group
        if chan in cp.channels.keys() and
        chan in signal.columns
    ]

    signal_chans = [
        chan
        for group in cp.groups.values()
        for chan in group
        if chan in cp.channels.keys() and
        chan in signal.columns
    ]
    data_chans = [
        data.channels[chan]
        for chan in signal_chans
    ]

    corr = [
        _spearmanr_nan(
            row[data_chans].as_matrix().ravel(),
            signal[signal_chans].as_matrix().ravel(),
        )
        for _, row in cp.psms.iterrows()
    ]

    cp.psms["Correlation"] = [i.correlation for i in corr]
    cp.psms["corr p-value"] = [i.pvalue for i in corr]

    f_corr, ax = plt.subplots(figsize=figsize)
    x, y, colors = [], [], []
    sig_x, sig_y, sig_labels = [], [], []

    for _, row in cp.psms.iterrows():
        if (
            row["Correlation"] == 0 or
            row["corr p-value"] == 0 or
            np.isinf(row["Correlation"]) or
            np.isnan(row["Correlation"]) or
            np.isinf(-np.log10(row["corr p-value"])) or
            np.isnan(-np.log10(row["corr p-value"]))
        ):
            continue

        x.append(row["Correlation"])
        y.append(-np.log10(row["corr p-value"]))

        if row["corr p-value"] < p:
            sig_x.append(row["Correlation"])
            sig_y.append(-np.log10(row["corr p-value"]))
            sig_labels.append(" / ".join(sorted(row["Proteins"].genes)))

        colors.append(
            "blue"
            if row["corr p-value"] < p else
            "{:.2f}".format(
                max([len(row[data_chans].dropna()) / len(data_chans) - .25, 0])
            )
        )

    ax.scatter(x, y, c=colors)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    texts = []
    for xs, ys, txt in zip(sig_x, sig_y, sig_labels):
        if any(i.strip() in hide for i in txt.split("/")):
            continue

        txt = rename.get(txt, txt)

        text = ax.text(
            xs, ys,
            txt[:20] + ("..." if len(txt) > 20 else ""),
        )

        if txt in highlight:
            text.set_fontsize(20)

        text.set_bbox(
            dict(
                facecolor="lightgreen" if xs > 0 else "pink",
                alpha=1,
                linewidth=0.5 if txt not in edgecolors else 3,
                edgecolor=edgecolors.get(txt, "black"),
                boxstyle="round",
            )
        )

        texts.append(text)

    adjust_text(
        x=sig_x,
        y=sig_y,
        texts=texts,
        ax=ax,
        lim=400,
        force_text=0.3,
        force_points=0.01,
        arrowprops=dict(arrowstyle="->", relpos=(0, 0), lw=1),
        only_move={
            "points": "y",
            "text": "xy",
        }
    )

    ax.set_xlabel(
        "Correlation",
        fontsize=20,
    )
    ax.set_yticklabels(
        "{:.3}".format(i)
        for i in np.power(1/10, ax.get_yticks())
    )
    ax.set_ylabel(
        "p-value",
        fontsize=20,
    )

    if title:
        ax.set_title(title, fontsize=32)

    cp.psms = cp.psms[cp.psms["corr p-value"] < p]

    f_scatter, axes = plt.subplots(
        int(np.ceil(cp.psms.shape[0] / 3)), 3,
        figsize=(18, cp.psms.shape[0] * 2),
    )

    for index, (ax, (_, row)) in enumerate(
        zip(
            axes.ravel(),
            cp.psms.sort_values("Correlation").iterrows(),
        )
    ):
        for data_chan, sig_chan, sig_group in zip(
            data_chans, signal_chans, signal_groups,
        ):
            ax.scatter(
                x=signal[sig_chan],
                y=row[data_chan],
                facecolors=scatter_colors.get(sig_group, "black"),
                edgecolors="black",
                marker=scatter_symbols.get(sig_group, "o"),
                s=200,
            )

        row_title = " / ".join(str(i.gene) for i in row["Proteins"])

        ax.set_title(
            row_title[:20] + ("..." if len(row_title) > 20 else ""),
            fontsize=28,
            fontweight="bold",
        )

        ax.set_xlabel(
            "{}\n$\\rho = {:.2f}; p = {:.2E}$".format(
                xlabel,
                row["Correlation"],
                row["corr p-value"],
            ),
            fontsize=22,
        )

        row_seq = str(row["Sequence"])
        row_mods = str(row["Modifications"].get_mods([(None, "Phospho")]))

        ax.set_ylabel(
            row_seq[:20] + (
                "..." if len(row_seq) > 20 else ""
            ) + (
                "\n({})".format(
                    row_mods[:20] + ("..." if len(row_mods) > 20 else "")
                ) if row_mods else ""
            ),
            fontsize=20,
        )
        for tick in ax.xaxis.get_major_ticks() + ax.yaxis.get_major_ticks():
            tick.label.set_fontsize(20)

    f_scatter.tight_layout(pad=2)

    return f_corr, f_scatter