from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"examples"))
from admission_comparison import confusion, far_contrast, paired_matrix


def test_common_population_confusion_and_paired_cells():
    truth = dict(a=True, b=True, c=False, d=False)
    left = dict(a=True, b=False, c=True, d=False)
    right = dict(a=True, b=True, c=False, d=False)
    result = confusion(truth, left)
    assert [result[k] for k in ("TP", "FP", "FN", "TN")] == [1, 1, 1, 1]
    assert result["FAR"] == dict(numerator=1, denominator=2, value=.5)
    assert paired_matrix(left, right, truth) == {"False_False": 1, "False_True": 1, "True_False": 1, "True_True": 1}
    with pytest.raises(ValueError, match="populations"):
        confusion(truth, {})
    assert confusion({}, {})["FAR"]["value"] is None


def test_hand_calculated_fixed_denominator_cluster_contrast():
    rows = [dict(source=str(i), acceptable=False, a=False, b=True) for i in range(2)]
    result = far_contrast(rows, draws=32)
    assert result["difference"] == result["low"] == result["high"] == -1
    assert result["pvalue"] == .5 and result["negatives"] == 2
    assert result == far_contrast(rows, draws=32)
    assert far_contrast(rows[:1])["status"] == "insufficient_clusters"
    assert far_contrast([dict(rows[0], acceptable=True)])["status"] == "undefined"
    with pytest.raises(ValueError, match="positive"):
        far_contrast(rows, draws=0)
    with pytest.raises(ValueError, match="16"):
        far_contrast([dict(rows[0], source=str(i)) for i in range(17)])
