"""
FTIR Contamination Analyzer - the benchmark's buckets and margins

What counts as right and wrong is PROTOCOL.md; this file is that text as code.

    bucket             the bucket of one answer
    wilson             95% interval of a share
    cluster_interval   95% interval when spectra are not independent
    margin             the interval reported for a data set
    without_lead       the verdict rule with the lead taken out, from stored scores

Short names used in this file:
    k = how many    n = out of how many

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import math

import numpy as np

from ftir_analyzer import config
from ftir_analyzer.analysis import PROBABLE
from ftir_analyzer.families import family_of

from .sets import IN, OPEN_SPECY, OUT, RELATIVE

SEED = 20261105
RESAMPLES = 2000
RIGHT, RIGHT_FAMILY, WRONG, NO_ANSWER = "right", "right family", "wrong", "no answer"
FALSE_PROBABLE, HELD_BACK = "false probable", "held back"
RELATIVE_NAMED = "relative named"
Z = 1.959963984540054                                      # 95%


def same_family(first, second):
    """True if two materials are in one family of data/families.csv."""
    family = family_of(first)
    return bool(family) and family == family_of(second)


def bucket(kind, verdict, named, truth, relative=""):
    """The bucket of one answer. named = the material group the verdict names."""
    if kind == OUT:
        return FALSE_PROBABLE if verdict == PROBABLE else HELD_BACK
    if verdict != PROBABLE:
        return NO_ANSWER
    if kind == RELATIVE:
        return RELATIVE_NAMED if named == relative else WRONG
    if named == truth:
        return RIGHT
    return RIGHT_FAMILY if same_family(named, truth) else WRONG


def wilson(k, n):
    """The 95% Wilson interval of k out of n: (low, high). It stays sensible at 0 of n, where k/n alone says 0."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    centre = (p + Z ** 2 / (2 * n)) / (1 + Z ** 2 / n)
    half = Z * math.sqrt(p * (1 - p) / n + Z ** 2 / (4 * n ** 2)) / (1 + Z ** 2 / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def cluster_interval(hits, clusters, seed=SEED, resamples=RESAMPLES):
    """A 95% bootstrap interval that resamples whole clusters, so spectra of one source move together."""
    names, index = np.unique(np.asarray(clusters), return_inverse=True)
    if len(names) == 0:
        return (0.0, 1.0)
    k = np.bincount(index, weights=np.asarray(hits, float), minlength=len(names))
    n = np.bincount(index, minlength=len(names)).astype(float)
    picks = np.random.default_rng(seed).integers(0, len(names), size=(resamples, len(names)))
    shares = k[picks].sum(axis=1) / n[picks].sum(axis=1)
    low, high = np.percentile(shares, [2.5, 97.5])
    return (float(low), float(high))


def margin(hits, clusters, dataset):
    """The interval the report gives: Wilson for the fibres; for Open Specy the wider of Wilson and the bootstrap."""
    k, n = int(np.sum(hits)), len(hits)
    low, high = wilson(k, n)
    if dataset == OPEN_SPECY and n:
        low_b, high_b = cluster_interval(hits, clusters)
        low, high = min(low, low_b), max(high, high_b)
    return (low, high)


def without_lead(r):
    """True if the rule would say 'probable' with the lead over the next material taken out."""
    return r >= config.PROBABLE_R


__all__ = ["IN", "OUT", "RELATIVE", "bucket", "wilson", "cluster_interval", "margin", "without_lead", "same_family"]
