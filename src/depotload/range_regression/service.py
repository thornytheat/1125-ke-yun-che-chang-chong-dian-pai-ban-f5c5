from math import fsum
from .fitting import finite_sample_band, forecast, train
from .contracts import ResidualScore

def recalibrate(history, ridge=2.0):
    return train(history, ridge)

def estimate_vehicle(model, route_km, estimated_climb, ambient_c, drive_minutes):
    recovery = max(0.0, 15 - ambient_c) * drive_minutes / 60
    return forecast(model, (route_km, estimated_climb / 100, recovery))

def calibration_summary(model, history) -> ResidualScore:
    observed = len(history.held_out)
    if not observed:
        return ResidualScore.empty()
    pad = finite_sample_band(model.calibration, .8)
    errors = [abs(record.response - model.predict_center(record.features))
              for record in history.held_out]
    covered = sum(error <= pad for error in errors) if pad is not None else 0
    return ResidualScore(round(fsum(errors) / observed, 3),
                         covered / observed if pad is not None else None, observed, covered)
