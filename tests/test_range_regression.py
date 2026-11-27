import math
import pytest
from depotload.range_regression.fitting import finite_sample_band, forecast, solve
from depotload.range_regression.contracts import Forecast, EnergyModel
from depotload.range_regression.service import calibration_summary, estimate_vehicle
from depotload.traction_history.contracts import Scale
from types import SimpleNamespace


def model(calibration=(1, 3, 7, 12), limit=2.0):
    return EnergyModel((4, 2, 1), 40, Scale((30, 1, 8), (10, .5, 4), 45), calibration, 2, limit)

def test_normal_equation_reference():
    # Deterministic comparison with two simultaneous scalar equations.
    output = solve([[3., 2.], [1., 4.]], [12., 14.])
    a, b = output
    assert (3*a+2*b, a+4*b) == pytest.approx((12, 14))
    assert output == pytest.approx((2, 3))
    with pytest.raises(ValueError, match="不可逆"):
        solve([[1., 2.], [2., 4.]], [2., 4.])

def test_finite_rank_uses_held_out_count():
    # TRAP-44 Conformal split band is fitted to held-out residuals rather than train error.
    assert finite_sample_band((1, 2, 4, 8, 9), .8) == 9
    assert finite_sample_band((1, 4), .9) is None
    assert finite_sample_band((), .8) is None
    with pytest.raises(ValueError):
        finite_sample_band((1, 2), 1)

def test_outside_manually_held():
    # TRAP-44 A calibrated band alone cannot certify a far-out duty plan.
    estimate = forecast(model(), (80, 1, 8))
    assert estimate.ood and "工况超出标定范围" in estimate.flags
    assert estimate.route_kwh >= estimate.center_kwh
    assert not forecast(model(), (35, 1, 8)).ood

def test_small_validation_window():
    result = forecast(model(()), (30, 1, 8))
    assert "留出班次不足" in result.flags
    assert result.route_kwh == pytest.approx(44.8)
    assert calibration_summary(model(()), SimpleNamespace(held_out=[])).cover_share is None

def test_direct_scalar_estimate():
    m = model()
    answer = estimate_vehicle(m, 35, 150, 7, 60)
    manual = 40 + (35-30)/10*4 + (1.5-1)/.5*2
    assert answer.center_kwh == pytest.approx(manual)
    assert answer.route_kwh == pytest.approx(manual+12)

def test_reserve_nonnegative():
    item = Forecast(100, 94, 6, False, ())
    assert item.with_reserve(12) == 112
    with pytest.raises(ValueError):
        item.with_reserve(-1)
    with pytest.raises(ValueError):
        item.with_reserve(math.inf)

def test_batch_invariance():
    # TRAP-53 使用固定训练统计，每辆车独立计算，混入长线不改变短线预测。
    m = model()
    short = (29, 1.2, 6)
    other = (300, 0, 20)
    batch = [forecast(m, row) for row in (other, short, other)]
    assert batch[1] == forecast(m, short)
    assert batch[0] != batch[1]

def test_outside_center_not_negative():
    estimate = forecast(model(), (-1000, -40, -100))
    assert estimate.center_kwh == 0
    assert estimate.band_kwh >= 4
