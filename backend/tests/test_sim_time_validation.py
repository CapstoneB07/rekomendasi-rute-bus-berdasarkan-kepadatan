import pytest
from pydantic import ValidationError

from routers.rute import MAX_SIM_TIME_DETIK, MonteCarloRequest, RuteRequest

_RUTE = {"halte_asal": "A", "halte_tujuan": "B"}


@pytest.mark.parametrize("build", [lambda t: RuteRequest(**_RUTE, sim_time=t), lambda t: MonteCarloRequest(sim_time=t)])
def test_sim_time_batas_atas(build):
    assert build(0).sim_time == 0
    assert build(MAX_SIM_TIME_DETIK).sim_time == 86399
    for invalid in (MAX_SIM_TIME_DETIK + 1, 1_000_000_000, -1):
        with pytest.raises(ValidationError):
            build(invalid)
