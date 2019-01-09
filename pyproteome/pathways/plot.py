
from __future__ import division

import logging
import os
import warnings

import numpy as np
from matplotlib import pyplot as plt
import seaborn as sns

import pyproteome as pyp

from . import enrichments

LOGGER = logging.getLogger("pyp.pathways.plot")


def plot_nes_dist(nes_vals, nes_pi_vals):
    """
    Generate a histogram plot showing the distribution of NES(S) values
    alongside the distribution of NES(S, pi) values.

    Parameters
    ----------
    nes_vals : :class:`numpy.array`
    nes_pi_vals : :class:`numpy.array`

    Returns
    -------
    f : :class:`matplotlib.figure.Figure`
    ax : :class:`matplotlib.axes.Axes`
    """
    LOGGER.info("Plotting NES(S) and NES(S, pi) distributions")

    f, ax = plt.subplots(
        figsize=(4, 3),
    )

    if nes_pi_vals.shape[0] > 0:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=FutureWarning)
            sns.distplot(
                nes_pi_vals,
                color='k',
                ax=ax,
            )

    if nes_vals.shape[0] > 0:
        try:
            sns.distplot(
                nes_vals,
                color='r',
                hist=False,
                rug=True,
                kde=False,
                ax=ax,
            )
        except ValueError as err:
            LOGGER.warning("sns.distplot threw an error: {}".format(err))

    return f, ax


def plot_nes(
    vals,
    min_hits=0,
    min_abs_score=0,
    max_pval=.1,
    max_qval=1,
    figsize=None,
    title=None,
    col=None,
    ax=None,
):
    """
    Plot the ranked normalized enrichment score values.

    Annotates significant gene sets with their name on the figure.

    Parameters
    ----------
    vals : :class:`pandas.DataFrame`
        The gene sets and scores calculated by enrichment_scores().
    min_hits : int, optional
    min_abs_score : float, optional
    max_pval : float, optional
    max_qval : float, optional
    figsize : tuple of (int, int), optional

    Returns
    -------
    f : :class:`matplotlib.figure.Figure`
    ax : :class:`matplotlib.axes.Axes`
    """
    LOGGER.info("Plotting ranked NES(S) values")

    v = vals.copy()

    if col is None:
        col = [
            i
            for i in ['q-value', 'p-value', 'NES(S)', 'ES(S)']
            if i in v.columns
        ][0]

    if col in ['p-value']:
        sig_cutoff = -np.log10(.01)
    elif col in ['q-value']:
        sig_cutoff = -np.log10(.25)
    else:
        sig_cutoff = 1

    p_iter = len(v['ES(S, pi)'].iloc[0])

    if col in ['p-value', 'q-value']:
        v[col] = v[col].apply(
            lambda x:
            -np.log10(x) if x > 0 else -np.log10(1/p_iter)
        )

    v = v.sort_values('NES(S)', ascending=False)

    if ax is None:
        _, ax = plt.subplots(
            figsize=figsize or (5, 4 / 14 * v.shape[0]),
        )

    sns.barplot(
        data=v,
        x=col,
        y='name',
        ax=ax,
    )

    if title is not None:
        ax.set_title(title)

    ax.set_ylabel('')

    if col in ['p-value', 'q-value']:
        ax.set_xticks([
            i
            for i in ax.get_xticks()
            if abs(i - int(i)) < .1
        ])

    ax.set_xticklabels([
        '{:.3}'.format(10 ** -i)
        for i in ax.get_xticks()
    ])
    ax.axvline(sig_cutoff, color='k', linestyle=':')

    return ax.get_figure(), ax


def plot_correlations(gene_changes, figsize=None):
    """
    Plot the ranked list of correlations.

    Parameters
    ----------
    gene_changes : :class:`pandas.DataFrame`
        Genes and their correlation values as calculated by get_gene_changes().
    figsize : tuple of (int, int), optional

    Returns
    -------
    f : :class:`matplotlib.figure.Figure`
    ax : :class:`matplotlib.axes.Axes`
    """
    LOGGER.info("Plotting gene correlations")

    f, ax = plt.subplots(
        figsize=figsize or (4, 3),
    )

    ax.plot(
        gene_changes["Correlation"].sort_values(ascending=False).tolist(),
    )
    ax.axhline(0, color="k")

    ax.set_xlabel("Gene List Rank")
    ax.set_ylabel("Correlation")

    return f, ax


def plot_enrichment(
    vals,
    cols=5,
):
    """
    Plot enrichment score curves for each gene set.

    Parameters
    ----------
    vals : :class:`pandas.DataFrame`
        The gene sets and scores calculated by enrichment_scores().
    cols : int, optional
    """
    LOGGER.info("Plotting ES(S) graphs")

    rows = max([int(np.ceil(len(vals) / cols)), 1])
    scale = 3

    f, axes = plt.subplots(
        rows, cols,
        figsize=(scale * cols, scale * rows),
        squeeze=False,
        sharex=True,
        sharey=True,
    )
    axes = [i for j in axes for i in j]

    nes = "NES(S)" if "NES(S)" in vals.columns else "ES(S)"

    ax_iter = iter(axes)

    for index, (set_id, row) in enumerate(vals.iterrows()):
        ax = next(ax_iter)

        if (
            "cumscore" in row and
            len(row["cumscore"]) > 0 and
            row["hits"].any()
        ):
            ax.plot(row["cumscore"], color="g")

        if (
            "down_cumscore" in row and
            len(row["down_cumscore"]) > 0 and
            row["down_hits"].any()
        ):
            ax.plot(row["down_cumscore"], color="r")

        for ind, hit in enumerate(row["hits"]):
            if hit:
                ax.axvline(ind, linestyle=":", alpha=.25, color="g")

        if "down_hits" in row:
            for ind, hit in enumerate(row["down_hits"]):
                if hit:
                    ax.axvline(ind, linestyle=":", alpha=.25, color="r")

        name = row["name"]
        name = name if len(name) < 35 else name[:35] + "..."

        ax.set_title(
            name
        )
        txt = "hits: {} {}={:.2f}".format(
            row["n_hits"],
            nes.split("(")[0],
            row[nes],
        ) + (
            "\np={:.2f}".format(
                row["p-value"],
            ) if "p-value" in row.index else ""
        ) + (
            ", q={:.2f}".format(
                row["q-value"],
            ) if "q-value" in row.index else ""
        )

        ax.axhline(0, color="k")

        if index >= len(axes) - cols:
            ax.set_xlabel("Gene List Rank")

        if index % cols == 0:
            ax.set_ylabel("ES(S)")

        ax.set_ylim(-1, 1)

        ax.text(
            s=txt,
            x=ax.get_xlim()[1] / 2,
            y=-.8,
            zorder=10,
            color='k',
            horizontalalignment='center',
            verticalalignment='center',
            bbox=dict(
                alpha=1,
                linewidth=0.5,
                facecolor="white",
                zorder=1,
                edgecolor="black",
                boxstyle="round",
            )
        )

    for ax in ax_iter:
        ax.axis('off')

    return f, axes


def plot_gsea(
    vals, gene_changes,
    min_hits=0,
    min_abs_score=0,
    max_pval=1,
    max_qval=1,
    folder_name=None,
    name="",
    **kwargs
):
    """
    Run set enrichment analysis on a data set and generate all figures
    associated with that analysis.

    Parameters
    ----------
    vals : :class:`pandas.DataFrame`
    gene_changes : :class:`pandas.DataFrame`

    Returns
    -------
    figs : list of :class:`matplotlib.figure.Figure`
    """
    folder_name = pyp.utils.make_folder(
        sub="GSEA + PSEA",
        folder_name=folder_name,
    )

    figs = ()

    figs += plot_correlations(gene_changes)[0],

    if vals.shape[0] > 0:
        figs += plot_enrichment(
            enrichments.filter_vals(
                vals,
                min_abs_score=min_abs_score,
                max_pval=max_pval,
                max_qval=max_qval,
                min_hits=min_hits,
            ),
            **kwargs
        )[0],

        if "NES(S)" in vals.columns:
            figs += plot_nes(
                vals,
                min_hits=min_hits,
                min_abs_score=min_abs_score,
                max_pval=max_pval,
                max_qval=max_qval,
            )[0],

    for index, fig in enumerate(figs):
        fig_path = os.path.join(folder_name, name + "-{}.png".format(index))

        fig.savefig(
            fig_path,
            bbox_inches="tight",
            dpi=pyp.DEFAULT_DPI,
            transparent=True,
        )
        LOGGER.info(
            'Saved figure to {}'.format(fig_path)
        )

    return figs