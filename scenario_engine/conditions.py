"""Turn a set of qualifying outcomes into exact, readable conditions.

Given the outcomes under which something happens -- a subset of all possible
win/loss combinations -- describe that subset exactly.

The previous approach intersected the qualifying outcomes elementwise and kept
whatever they agreed on. That produces a *necessary* condition, which is only
also *sufficient* when the set happens to be a full sub-cube. When it isn't,
outcomes that satisfy every stated condition are not actually qualifying ones,
so the report overclaims. Worse, a set with nothing at all in common intersects
to no conditions and reads as unconditional.

This computes a minimal disjunctive normal form instead (Quine-McCluskey plus a
greedy cover). Every implicant is a subset of the qualifying set by
construction, and together they cover it, so the description is exactly the set
-- never broader. An unconditional result falls out naturally: the full cube
collapses to a single implicant with no conditions.
"""


def _prime_implicants(minterms, num_vars):
    """Combine outcomes that differ in one variable until nothing more merges.

    An implicant is (value, care_mask): bits set in care_mask are pinned to the
    matching bits of value, the rest are don't-cares.
    """
    full_care = (1 << num_vars) - 1
    groups = {(m, full_care) for m in minterms}
    primes = set()

    while groups:
        merged = set()
        combined = set()
        group_list = sorted(groups)
        for i in range(len(group_list)):
            value_a, care_a = group_list[i]
            for j in range(i + 1, len(group_list)):
                value_b, care_b = group_list[j]
                if care_a != care_b:
                    continue
                diff = (value_a ^ value_b) & care_a
                # exactly one cared bit differs -> that bit becomes don't-care
                if diff and diff & (diff - 1) == 0:
                    merged.add(group_list[i])
                    merged.add(group_list[j])
                    combined.add((value_a & ~diff, care_a & ~diff))
        primes.update(g for g in group_list if g not in merged)
        groups = combined

    return primes


def _outcomes_matching(implicant, minterms):
    value, care = implicant
    return {m for m in minterms if m & care == value}


def _greedy_cover(primes, minterms):
    """Pick implicants until every qualifying outcome is covered."""
    remaining = set(minterms)
    chosen = []
    while remaining:
        best = max(
            primes,
            key=lambda p: (len(_outcomes_matching(p, minterms) & remaining), -p[1]),
        )
        covered = _outcomes_matching(best, minterms)
        if not covered & remaining:  # defensive: cannot happen for prime implicants
            break
        chosen.append(best)
        remaining -= covered
    return chosen


def minimal_dnf(minterms, num_vars):
    """Describe `minterms` exactly as a list of implicants.

    `minterms` is a set of ints, each a bitmask over `num_vars` variables.
    Returns a list of dicts {variable_index: bit}, only for pinned variables.

    - `[]`            -- the set is empty; this never happens
    - `[{}]`          -- every outcome qualifies; unconditional
    - anything else   -- alternatives, any one of which suffices
    """
    minterms = set(minterms)
    if not minterms:
        return []
    if num_vars == 0:
        return [{}]

    primes = _prime_implicants(minterms, num_vars)
    implicants = []
    for value, care in _greedy_cover(primes, minterms):
        implicants.append(
            {bit: (value >> bit) & 1 for bit in range(num_vars) if care >> bit & 1}
        )
    # Fewest conditions first, so the easiest path to read comes first
    implicants.sort(key=lambda d: (len(d), sorted(d.items())))
    return implicants


def describes_exactly(implicants, minterms, num_vars):
    """True if `implicants` covers `minterms` and nothing else.

    Used by the tests as an independent check on minimal_dnf.
    """
    described = set()
    for outcome in range(1 << num_vars):
        for implicant in implicants:
            if all((outcome >> bit) & 1 == value for bit, value in implicant.items()):
                described.add(outcome)
                break
    return described == set(minterms)
