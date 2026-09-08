"""전략 설정(dataclass) 및 YAML 로더."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, asdict, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SyntheticConfig:
    """기준(무레버리지) 지수에서 레버리지 ETF 가격을 합성할 때 쓰는 파라미터."""
    leverage: float = 3.0
    beta: float = 1.0              # 기준 지수 대비 민감도 (반도체≈나스닥×1.3 같은 스트레스용)
    expense_ratio: float = 0.0095  # 연 보수 (SOXL 0.95%)
    financing_rate: float = 0.02   # 연 조달금리 (레버리지-1 배만큼 부담)


@dataclass
class DataConfig:
    symbol: str = "SOXL"          # 매매 대상 (레버리지 ETF)
    reference: str = "SOXX"       # 추세/변동성 판단용 기준 지수(무레버리지)
    source: str = "yfinance"      # yfinance | csv | bundled
    cache_dir: str = "data/cache"
    bundled_dir: str = "data/bundled"
    start: str | None = None      # 매매 시작일 (지표 계산은 그 이전 데이터도 사용)
    end: str | None = None
    synthetic: SyntheticConfig | None = None   # 설정 시 symbol 가격을 reference로부터 합성
    backfill: bool = False        # 실제 ETF 상장 이전 구간을 합성 가격으로 연장


@dataclass
class BasketConfig:
    count: int = 5                     # 동시 운용 바스켓 수 = 자산 분할 수
    slices: int = 8                    # 바스켓 예산을 나눠 사는 분할 매수 횟수
    min_days_between_opens: int = 3    # 바스켓 신규 오픈 간 최소 간격(거래일) → 진입 시점 분산
    min_budget_frac: float = 0.25      # 여유 현금이 정상 예산의 이 비율 미만이면 오픈하지 않음
    budget_frac: float | None = None   # 바스켓 예산 = 총자산 × budget_frac (None = 1/count). 합이 1을 넘으면 현금 한도로 제한
    budget_mode: str = "equity"        # equity: 현재 총자산 기준(복리) | fixed: 초기자본 기준 고정(단리)


@dataclass
class EntryConfig:
    vol_window: int = 20               # 일간 실현변동성 산출 창
    dip_vol_mult: float = 0.5          # 매수 LOC 지정가 = 전일종가 × (1 − mult × 일변동성)
    min_dip_pct: float = 0.01
    max_dip_pct: float = 0.06
    first_slice_dip_pct: float = 0.0   # 바스켓 첫 슬라이스는 이 하락률만 요구 (0 = 보합 이하면 매수)
    first_slice_mult: float = 1.0      # 첫 슬라이스 크기 배수
    depth_boost: float = 0.0           # 평단 대비 −10%마다 슬라이스 배수 가산 (물타기 가속, 0=비활성)
    max_slice_mult: float = 3.0
    target_vol: float | None = None    # 변동성 타게팅: 슬라이스 × min(1, target_vol/σ). 급변동기 매수 축소 (예: 0.04)
    addon_below_avg_pct: float | None = None  # 2번째 슬라이스부터는 지정가 ≤ 평단 × (1 − 이 값) 일 때만 (v5 의 −5% 물타기 규칙)


@dataclass
class ExitConfig:
    lot_tp_vol_mult: float = 1.5       # 로트 매도 LOC 지정가 = 로트 매입가 × (1 + mult × 일변동성)
    min_lot_tp_pct: float = 0.03
    max_lot_tp_pct: float = 0.15
    lot_tp_sell_frac: float = 1.0      # 로트 익절 시 매도 비율 (0.5 = 절반만 팔고 나머지는 바스켓 청산까지 보유)
    upday_sell_frac: float = 0.0       # 상승 마감일마다 보유수량의 이 비율을 매도 (LOC 지정가 = 전일종가). invest_strategy v5 의 부분매도
    upday_min_rise: float = 0.0        # 상승일 판정 최소 상승률 (LOC 지정가 = 전일종가 × (1 + 이 값))
    basket_tp_pct: float = 0.10        # 바스켓 수익률(예산 대비) 목표 → 전량 청산(MOC)
    basket_sl_pct: float | None = 0.35 # 바스켓 손실률 한도 → 전량 청산 (None=미사용)
    max_hold_days: int = 60            # 보유기간 초과 시, 손익 ≥ soft_exit_pnl_pct 이면 청산
    hard_max_hold_days: int = 120      # 보유기간 초과 시 무조건 청산
    soft_exit_pnl_pct: float = 0.0


@dataclass
class RegimeConfig:
    enabled: bool = True
    ma_window: int = 200               # 기준 지수 종가 vs 이동평균 → 강세/약세
    ma_band: float = 0.0               # 히스테리시스 밴드: 강세 전환은 MA×(1+band) 상향, 약세 전환은 MA×(1−band) 하향 돌파
    bear_max_baskets: int = 2          # 약세장에서 동시 운용 가능한 바스켓 수
    bear_slice_mult: float = 0.5       # 약세장 슬라이스 크기 배수
    bear_no_new_lots: bool = False     # 약세장에서는 신규 매수 자체를 중단
    bear_liquidate: bool = False       # 약세 전환 시 bear_max_baskets 초과분(수익률 낮은 순)을 청산
    cooldown_after_sl_days: int = 0           # 바스켓 손절 후 이 기간 동안 신규 바스켓 오픈 금지
    breaker_dd: float | None = None           # 계좌 서킷브레이커: 총자산이 고점 대비 이 비율 이상 빠지면 전량 청산·매매 중단 (예: 0.15)
    breaker_resume_sma: int = 200             # 중단 해제: 매매 대상 종가가 이 이동평균 위로 복귀하면 재개 (고점은 현재 자산으로 리셋)
    max_vol_to_open: float | None = None      # 일변동성이 이 값 초과면 신규 바스켓 오픈 금지 (예: 0.06)


@dataclass
class RiskConfig:
    """포트폴리오 단위 노출 관리 (심리적 방어 레이어)."""
    vol_target_annual: float | None = None   # 노출 상한 = min(1, 목표연변동성 / 매매대상 실현연변동성). 예: 0.35
    max_exposure: float = 1.0                # 총자산 대비 투자비중 절대 상한
    dd_scale_start: float | None = None      # 전략 자산 낙폭이 이 값을 넘으면 매수 규모 축소 시작 (예: 0.10)
    dd_scale_floor: float = 0.30             # 이 낙폭에서 축소가 최대가 됨
    dd_scale_min_mult: float = 0.25          # 최대 축소 시 매수 규모 배수


@dataclass
class CostConfig:
    commission_pct: float = 0.0007     # 편도 수수료 (0.07%)
    slippage_pct: float = 0.0          # 종가 체결이므로 기본 0
    integer_shares: bool = False       # True: 정수 주만 체결 (1주 미만 주문은 건너뜀). 소액 계좌 검토용


@dataclass
class StrategyConfig:
    name: str = "basket_loc"
    initial_capital: float = 100_000.0
    cash_yield_annual: float = 0.0     # 대기 현금 수익률 (예: 단기채 ETF 파킹 시 0.04)
    data: DataConfig = field(default_factory=DataConfig)
    baskets: BasketConfig = field(default_factory=BasketConfig)
    entry: EntryConfig = field(default_factory=EntryConfig)
    exit: ExitConfig = field(default_factory=ExitConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    costs: CostConfig = field(default_factory=CostConfig)

    # ---- 직렬화 ----
    def to_dict(self) -> dict:
        return asdict(self)

    def copy(self) -> "StrategyConfig":
        return copy.deepcopy(self)

    def with_overrides(self, overrides: dict[str, Any]) -> "StrategyConfig":
        """{"exit.basket_tp_pct": 0.08, "baskets.count": 4} 형태의 점 표기 오버라이드."""
        cfg = self.copy()
        for path, value in overrides.items():
            obj = cfg
            parts = path.split(".")
            for p in parts[:-1]:
                obj = getattr(obj, p)
            if not hasattr(obj, parts[-1]):
                raise KeyError(f"unknown config path: {path}")
            setattr(obj, parts[-1], value)
        return cfg


_NESTED = {
    "data": DataConfig, "baskets": BasketConfig, "entry": EntryConfig,
    "exit": ExitConfig, "regime": RegimeConfig, "risk": RiskConfig, "costs": CostConfig,
}


def _build(cls, raw: dict | None):
    raw = dict(raw or {})
    kwargs = {}
    valid = {f.name for f in fields(cls)}
    for k, v in raw.items():
        if k not in valid:
            raise KeyError(f"{cls.__name__}: unknown key '{k}'")
        kwargs[k] = v
    if cls is DataConfig and kwargs.get("synthetic") is not None:
        kwargs["synthetic"] = _build(SyntheticConfig, kwargs["synthetic"])
    return cls(**kwargs)


def config_from_dict(raw: dict) -> StrategyConfig:
    raw = dict(raw)
    kwargs = {}
    for key, cls in _NESTED.items():
        kwargs[key] = _build(cls, raw.pop(key, None))
    valid = {f.name for f in fields(StrategyConfig)}
    for k, v in raw.items():
        if k not in valid:
            raise KeyError(f"StrategyConfig: unknown key '{k}'")
        kwargs[k] = v
    return StrategyConfig(**kwargs)


def load_config(path: str | Path) -> StrategyConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return config_from_dict(raw)


def save_config(cfg: StrategyConfig, path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg.to_dict(), f, allow_unicode=True, sort_keys=False)
