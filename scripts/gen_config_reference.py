"""config.py 의 dataclass 필드·기본값·주석으로 docs/06_config_reference.md 를 생성한다.
사용: python scripts/gen_config_reference.py   (config.py 를 바꾸면 다시 실행)"""
import re, pathlib

SRC = pathlib.Path("src/qtrade/config.py").read_text(encoding="utf-8")
OUT = pathlib.Path("docs/06_config_reference.md")
SECTION = {"StrategyConfig": "최상위", "DataConfig": "data", "SyntheticConfig": "data.synthetic", "BasketConfig": "baskets",
           "EntryConfig": "entry", "ExitConfig": "exit", "RegimeConfig": "regime", "CostConfig": "costs"}
STATUS = {  # 프로필 코어 외 옵션의 용도
    "first_slice_dip_pct": "코어(0)", "basket_sl_pct": "기각(해로움) — None 유지", "soft_exit_pnl_pct": "코어(0)",
    "breaker_dd": "공격형만", "ma_band": "코어(0)", "integer_shares": "검토용", "slippage_pct": "실측 후 설정",
    "synthetic": "프록시용", "backfill": "백필용", "budget_mode": "비교용(fixed)",
}
blocks = re.findall(r"@dataclass\nclass (\w+):\n(.*?)(?=\n\n\n|\n@dataclass|\n_NESTED)", SRC, flags=re.S)
lines = ["# 06. 설정 레퍼런스 (자동 생성: `python scripts/gen_config_reference.py`)", "",
         "YAML 은 `qtrade make-configs` 가 `src/qtrade/profiles.py` 에서 생성한다. 기본값은 **균형형 프로필과 같다**(테스트로 강제).",
         "기각된 실험 옵션(손절, 물타기 가속, 부분 익절, 변동성 레짐, 노출 상한, 낙폭 연동 축소, 레짐 판정 방식 등)은 2026-09-21 정리 시 코드에서 제거했다. 근거와 수치는 docs/02 §3, docs/07 §4 에 남아 있다.", ""]
for cls, body in blocks:
    lines += [f"## `{SECTION.get(cls, cls)}` ({cls})", "", "| 키 | 기본값 | 의미 | 상태 |", "|---|---|---|---|"]
    for line in body.splitlines():
        m = re.match(r"\s{4}(\w+):\s*([^=]+?)\s*=\s*(.+?)(?:\s{2,}#\s*(.*))?$", line)
        if not m or line.strip().startswith(("def ", "#", '"')):
            continue
        f, _t, default, comment = m.groups()
        if default.startswith("field("):
            default = "(하위 섹션)"
        lines.append(f"| `{f}` | `{default.strip()}` | {(comment or '').strip()} | {STATUS.get(f, '')} |")
    lines.append("")
lines += ["## 점 표기 오버라이드", "", "탐색 그리드와 `with_overrides` 는 `섹션.키` 형태를 쓴다. 예: `exit.upday_sell_frac: 0.2`, `regime.breaker_dd: 0.25`.", ""]
OUT.write_text("\n".join(lines), encoding="utf-8")
print("wrote", OUT)
