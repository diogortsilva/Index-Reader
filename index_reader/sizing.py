"""Cable size proposal: how many pairs or triads, split across how many cables."""

from __future__ import annotations

from . import config


def required_capacity(used, spare_percent=None, spare_min_used=None):
    """Capacity needed for `used` pairs/triads including the spare rule.

    Fewer than `spare_min_used` in use: no spare required.
    Otherwise: used * (1 + spare%), rounded up. Integer maths only.
    """
    if spare_percent is None:
        spare_percent = config.SPARE_PERCENT
    if spare_min_used is None:
        spare_min_used = config.SPARE_MIN_USED
    if used <= 0:
        return 0
    if used < spare_min_used:
        return used
    return -(-(used * (100 + spare_percent)) // 100)


def choose_cables(required, sizes):
    """Pick standard cables whose capacities add up to at least `required`.

    Rules, in this order:
      1. fewest cables
      2. least total capacity
      3. largest cable first
    Returns a list of sizes, largest first (empty when required is 0).
    """
    if required <= 0:
        return []
    sizes = sorted(set(int(s) for s in sizes))
    if not sizes:
        raise ValueError("no cable sizes configured")
    biggest = sizes[-1]
    limit = required + biggest
    inf = float("inf")
    # fewest[t] = fewest cables whose capacities add up to exactly t
    fewest = [inf] * (limit + 1)
    fewest[0] = 0
    for t in range(1, limit + 1):
        best = inf
        for s in sizes:
            if s <= t and fewest[t - s] + 1 < best:
                best = fewest[t - s] + 1
        fewest[t] = best
    target = None
    for t in range(required, limit + 1):
        if fewest[t] == inf:
            continue
        if target is None or fewest[t] < fewest[target]:
            target = t
    if target is None:  # cannot happen when the size list is non-empty
        raise ValueError("cannot build capacity %d from sizes %r" % (required, sizes))
    picked = []
    t = target
    while t > 0:
        for s in reversed(sizes):
            if s <= t and fewest[t - s] == fewest[t] - 1:
                picked.append(s)
                t -= s
                break
    return picked


def format_cables(cables, unit):
    """[24, 12], 'PR' -> '1-24 PR + 1-12 PR'; [12, 12] -> '2-12 PR'."""
    parts = []
    seen = []
    for size in cables:
        if size not in seen:
            seen.append(size)
    for size in seen:
        parts.append("%d-%d %s" % (cables.count(size), size, unit))
    return " + ".join(parts)


class Proposal(object):
    """Sizing result for one cable run."""

    def __init__(self, used_pairs, used_triads):
        self.used_pairs = used_pairs
        self.used_triads = used_triads
        self.required_pairs = required_capacity(used_pairs)
        self.required_triads = required_capacity(used_triads)
        self.pair_cables = choose_cables(self.required_pairs, config.PAIR_SIZES)
        self.triad_cables = choose_cables(self.required_triads, config.TRIAD_SIZES)

    @property
    def pair_capacity(self):
        return sum(self.pair_cables)

    @property
    def triad_capacity(self):
        return sum(self.triad_cables)

    @property
    def text(self):
        parts = []
        if self.pair_cables:
            parts.append(format_cables(self.pair_cables, "PR"))
        if self.triad_cables:
            parts.append(format_cables(self.triad_cables, "TR"))
        return " + ".join(parts)

    @property
    def cable_count(self):
        return len(self.pair_cables) + len(self.triad_cables)

    @property
    def spare_text(self):
        parts = []
        if self.pair_cables:
            parts.append("%d PR" % (self.pair_capacity - self.used_pairs))
        if self.triad_cables:
            parts.append("%d TR" % (self.triad_capacity - self.used_triads))
        return " + ".join(parts)

    @property
    def spare_fraction(self):
        """Spare as a fraction of what is in use (None when nothing is used)."""
        used = self.used_pairs + self.used_triads
        if not used:
            return None
        cap = self.pair_capacity + self.triad_capacity
        return float(cap - used) / used
