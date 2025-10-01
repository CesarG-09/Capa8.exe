from dataclasses import dataclass
from datetime import datetime, time, timedelta, date
from typing import Dict, List, Optional, Tuple, Iterable, Protocol


class DemandProvider(Protocol):
    def get_demand_score(self, route_name: str, at: datetime) -> float: ...


class HeadwayPolicy(Protocol):
    def get_headway_minutes(self, route_name: str, at: datetime, demand_score: float) -> int: ...


@dataclass
class SimpleDemandByHour:
    by_hour: Dict[int, float] = None
    base: float = 0.4

    def __post_init__(self):
        if self.by_hour is None:
            self.by_hour = {
                **{h: 0.25 for h in range(0, 5)},
                **{h: 0.6 for h in range(5, 7)},
                **{h: 0.9 for h in range(7, 9)},
                **{h: 0.5 for h in range(9, 12)},
                **{12: 0.7, 13: 0.7},
                **{h: 0.55 for h in range(14, 17)},
                **{h: 0.95 for h in range(17, 20)},
                **{h: 0.4 for h in range(20, 24)},
            }

    def get_demand_score(self, route_name: str, at: datetime) -> float:
        return float(max(0.0, min(1.0, self.by_hour.get(at.hour, self.base))))


@dataclass
class ThresholdHeadwayPolicy:
    thresholds: List[Tuple[float, int]] = None
    min_headway: int = 6
    max_headway: int = 60

    def __post_init__(self):
        if self.thresholds is None:
            self.thresholds = [
                (0.85, 8),
                (0.70, 10),
                (0.50, 15),
                (0.30, 20),
                (0.00, 30),
            ]
        self.thresholds.sort(key=lambda x: x[0], reverse=True)

    def get_headway_minutes(self, route_name: str, at: datetime, demand_score: float) -> int:
        for thr, hw in self.thresholds:
            if demand_score >= thr:
                return int(max(self.min_headway, min(self.max_headway, hw)))
        return int(max(self.min_headway, min(self.max_headway, self.thresholds[-1][1])))


@dataclass
class ServiceWindow:
    start: time
    end: time

    def contains(self, dt: datetime) -> bool:
        return self.start <= dt.time() <= self.end


@dataclass
class ScheduleOptions:
    service_window: ServiceWindow
    fixed_headway_min: Optional[int] = None
    round_to_minutes: Optional[int] = 5


def _round_dt(dt: datetime, round_to_minutes: Optional[int]) -> datetime:
    if not round_to_minutes or round_to_minutes <= 1:
        return dt
    discard = timedelta(
        minutes=dt.minute % round_to_minutes,
        seconds=dt.second,
        microseconds=dt.microsecond,
    )
    return dt - discard


def generate_daily_schedule(
    routes: Iterable[str],
    service_day: date,
    options: ScheduleOptions,
    demand_provider: Optional[DemandProvider] = None,
    headway_policy: Optional[HeadwayPolicy] = None,
) -> Dict[str, List[datetime]]:
    if options.service_window.start >= options.service_window.end:
        raise ValueError("La hora de inicio debe ser menor que la de fin.")

    dp = demand_provider or SimpleDemandByHour()
    hp = headway_policy or ThresholdHeadwayPolicy()

    schedules: Dict[str, List[datetime]] = {r: [] for r in routes}

    for route in routes:
        current = datetime.combine(service_day, options.service_window.start)
        current = _round_dt(current, options.round_to_minutes)

        while current.time() <= options.service_window.end:
            schedules[route].append(current)

            if options.fixed_headway_min is not None:
                headway_min = options.fixed_headway_min
            else:
                demand = dp.get_demand_score(route, current)
                headway_min = hp.get_headway_minutes(route, current, demand)

            current += timedelta(minutes=headway_min)
            if options.round_to_minutes:
                current = _round_dt(current, options.round_to_minutes)

    return schedules


def schedule_to_strings(schedule: Dict[str, List[datetime]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for route, times in schedule.items():
        out[route] = [dt.strftime("%H:%M") for dt in times]
    return out


# ------------------------------
# Ejemplo ficticio de uso de la applicación
# ------------------------------

if __name__ == "__main__":
    rutas_demo = ["Ruta_Centro", "Ruta_Estudiantil", "Ruta_Norte"]
    ventana = ServiceWindow(start=time(6, 0), end=time(22, 0))
    opts = ScheduleOptions(service_window=ventana, fixed_headway_min=None, round_to_minutes=5)

    demanda = SimpleDemandByHour()
    politica = ThresholdHeadwayPolicy()

    hoy = date.today()
    horario = generate_daily_schedule(
        routes=rutas_demo,
        service_day=hoy,
        options=opts,
        demand_provider=demanda,
        headway_policy=politica,
    )

    as_text = schedule_to_strings(horario)
    for ruta, salidas in as_text.items():
        print(f"\n{ruta} -> {len(salidas)} salidas")
        print(", ".join(salidas[:24]), "...")
