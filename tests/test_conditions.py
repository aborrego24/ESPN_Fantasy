"""The stated conditions must describe the qualifying outcomes exactly.

Not merely necessary -- exactly. An outcome satisfying every stated condition
must actually be a qualifying one, otherwise the report overclaims.
"""

import itertools
import random

import pytest

import conditions


@pytest.mark.parametrize("num_vars", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("seed", range(12))
def test_dnf_describes_the_set_exactly(num_vars, seed):
    rng = random.Random(seed * 100 + num_vars)
    universe = list(range(1 << num_vars))
    size = rng.randint(1, len(universe))
    minterms = set(rng.sample(universe, size))

    implicants = conditions.minimal_dnf(minterms, num_vars)

    assert conditions.describes_exactly(implicants, minterms, num_vars)


@pytest.mark.parametrize("num_vars", [1, 2, 3, 4])
def test_every_subset_is_described_exactly(num_vars):
    """Exhaustive over all subsets, not just sampled ones."""
    universe = list(range(1 << num_vars))
    for size in range(1, len(universe) + 1):
        for combo in itertools.combinations(universe, size):
            minterms = set(combo)
            implicants = conditions.minimal_dnf(minterms, num_vars)
            assert conditions.describes_exactly(implicants, minterms, num_vars), (
                f"{num_vars} vars, minterms={sorted(minterms)} -> {implicants}"
            )


@pytest.mark.parametrize("num_vars", [0, 1, 2, 3, 4])
def test_full_set_is_unconditional(num_vars):
    """Every outcome qualifies -> one alternative, with no conditions."""
    minterms = set(range(1 << num_vars))

    assert conditions.minimal_dnf(minterms, num_vars) == [{}]


@pytest.mark.parametrize("num_vars", [0, 1, 3])
def test_empty_set_has_no_alternatives(num_vars):
    assert conditions.minimal_dnf(set(), num_vars) == []


def test_a_single_outcome_pins_every_variable():
    # 0b101 over 3 variables
    assert conditions.minimal_dnf({0b101}, 3) == [{0: 1, 1: 0, 2: 1}]


def test_one_variable_that_does_not_matter_is_dropped():
    # Both values of bit 1 qualify while bit 0 is pinned -> only bit 0 stated.
    assert conditions.minimal_dnf({0b01, 0b11}, 2) == [{0: 1}]


def test_disjoint_alternatives_are_kept_separate():
    """A set that is not a single cube needs more than one alternative."""
    # Exactly one of two variables set -- classic XOR, not expressible as one cube
    implicants = conditions.minimal_dnf({0b01, 0b10}, 2)

    assert len(implicants) == 2
    assert conditions.describes_exactly(implicants, {0b01, 0b10}, 2)


def test_simplest_alternative_comes_first():
    # {0b00, 0b01, 0b10} -> "bit1 clear" (1 condition) or "bit0 clear"
    implicants = conditions.minimal_dnf({0b00, 0b01, 0b10}, 2)

    assert len(implicants[0]) <= len(implicants[-1])
