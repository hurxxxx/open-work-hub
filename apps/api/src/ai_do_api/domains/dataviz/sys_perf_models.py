"""시스템 성능(System Performance) — 레거시 sys_perf.db 14개 테이블을 Postgres 모델로 포팅.

레거시는 단일 SQLite. 여기서는 멀티워크스페이스 앱에 맞춰 모든 테이블에 workspace_id 를
추가하고 sysperf_ 접두어를 붙인다. 레거시가 정수 ID(refrigerant_id, file_id, /db-csv/<id>
등)를 참조하므로 PK 는 정수 autoincrement 를 유지한다. TEXT→Text, REAL→Float,
datetime('now','localtime') 기본값은 앱 로컬 타임스탬프 문자열로 대체(라우트가 문자열로 다룸).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ai_do_api.core.db import Base


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SysPerfStandardColumn(Base):
    __tablename__ = "sysperf_standard_columns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    standard_name: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[str] = mapped_column(Text, default="", nullable=False)
    unit: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(Text, default="general", nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SysPerfRefrigerantMaster(Base):
    __tablename__ = "sysperf_refrigerant_master"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_sysperf_refrigerant_master_ws_name"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    formula: Mapped[str] = mapped_column(Text, default="", nullable=False)


class SysPerfRefrigerantProp(Base):
    __tablename__ = "sysperf_refrigerant_props"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    refrigerant_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    sat_pressure_kgcm2: Mapped[float | None] = mapped_column(Float, nullable=True)
    sat_pressure_kpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    sat_pressure_bar: Mapped[float | None] = mapped_column(Float, nullable=True)
    liq_enthalpy: Mapped[float | None] = mapped_column(Float, nullable=True)
    vap_enthalpy: Mapped[float | None] = mapped_column(Float, nullable=True)
    liq_entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    vap_entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    liq_specific_vol: Mapped[float | None] = mapped_column(Float, nullable=True)
    vap_specific_vol: Mapped[float | None] = mapped_column(Float, nullable=True)


class SysPerfRefrigerantStatePoint(Base):
    __tablename__ = "sysperf_refrigerant_state_points"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    refrigerant_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    pressure_kpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_kgcm2: Mapped[float | None] = mapped_column(Float, nullable=True)
    sat_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    enthalpy: Mapped[float | None] = mapped_column(Float, nullable=True)
    entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    specific_vol: Mapped[float | None] = mapped_column(Float, nullable=True)


class SysPerfItemKeyword(Base):
    __tablename__ = "sysperf_item_keywords"
    __table_args__ = (
        UniqueConstraint("workspace_id", "item_n", name="uq_sysperf_item_keywords_ws_item"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    item_n: Mapped[int] = mapped_column(Integer, nullable=False)
    keywords: Mapped[str] = mapped_column(Text, default="", nullable=False)


class SysPerfCarModel(Base):
    __tablename__ = "sysperf_car_models"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    brand: Mapped[str] = mapped_column(Text, default="", nullable=False)
    era: Mapped[str] = mapped_column(Text, default="", nullable=False)
    year: Mapped[str] = mapped_column(Text, default="", nullable=False)
    car_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_code: Mapped[str] = mapped_column(Text, default="", nullable=False)
    segment_code: Mapped[str] = mapped_column(Text, default="", nullable=False)
    segment_name: Mapped[str] = mapped_column(Text, default="", nullable=False)
    refrigerant: Mapped[str] = mapped_column(Text, default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class SysPerfPartsCatalog(Base):
    __tablename__ = "sysperf_parts_catalog"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    drive_type: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sub_type: Mapped[str] = mapped_column(Text, default="", nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[str] = mapped_column(Text, default=_now_str, nullable=False)


class SysPerfPartsSpec(Base):
    __tablename__ = "sysperf_parts_spec"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, default="", nullable=False)
    car_code: Mapped[str] = mapped_column(Text, default="", nullable=False)
    comp: Mapped[str] = mapped_column(Text, default="", nullable=False)
    comp_prod: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    condenser: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cond_prod: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    txv: Mapped[str] = mapped_column(Text, default="", nullable=False)
    txv_prod: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    hvac: Mapped[str] = mapped_column(Text, default="", nullable=False)
    hvac_prod: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    pipe: Mapped[str] = mapped_column(Text, default="", nullable=False)
    pipe_prod: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    refrigerant_charge: Mapped[str] = mapped_column(Text, default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class SysPerfFileMaster(Base):
    __tablename__ = "sysperf_file_master"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    upload_date: Mapped[str] = mapped_column(Text, default=_now_str, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    sheet_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SysPerfTestMaster(Base):
    __tablename__ = "sysperf_test_master"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    file_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    filename: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sheet_name: Mapped[str] = mapped_column(Text, default="", nullable=False)
    saved_at: Mapped[str] = mapped_column(Text, default=_now_str, nullable=False)
    # 차량 정보
    car_code: Mapped[str] = mapped_column(Text, default="", nullable=False)
    car_type: Mapped[str] = mapped_column(Text, default="", nullable=False)
    engine: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stage: Mapped[str] = mapped_column(Text, default="", nullable=False)
    car_number: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 시험 정보
    test_item: Mapped[str] = mapped_column(Text, default="", nullable=False)
    test_date: Mapped[str] = mapped_column(Text, default="", nullable=False)
    refrigerant_charge: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 부품사양 12개
    comp: Mapped[str] = mapped_column(Text, default="", nullable=False)
    indoor_condenser: Mapped[str] = mapped_column(Text, default="", nullable=False)
    condenser: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cooling_fan: Mapped[str] = mapped_column(Text, default="", nullable=False)
    radiator: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ihx: Mapped[str] = mapped_column(Text, default="", nullable=False)
    txv: Mapped[str] = mapped_column(Text, default="", nullable=False)
    battery_chiller: Mapped[str] = mapped_column(Text, default="", nullable=False)
    eva: Mapped[str] = mapped_column(Text, default="", nullable=False)
    hvac: Mapped[str] = mapped_column(Text, default="", nullable=False)
    heater_core: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ptc: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 시계열 CSV 링크
    csv_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    col_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SysPerfSheetHeader(Base):
    __tablename__ = "sysperf_sheet_header"
    __table_args__ = (
        UniqueConstraint("workspace_id", "file_id", "sheet_name", name="uq_sysperf_sheet_header_scope"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    file_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_name: Mapped[str] = mapped_column(Text, nullable=False)
    header_row: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    info_row: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SysPerfTestInfo(Base):
    __tablename__ = "sysperf_test_info"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    file_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    sheet_name: Mapped[str] = mapped_column(Text, default="", nullable=False)
    car_code: Mapped[str] = mapped_column(Text, default="", nullable=False)
    car_model: Mapped[str] = mapped_column(Text, default="", nullable=False)
    spec: Mapped[str] = mapped_column(Text, default="", nullable=False)
    test_item: Mapped[str] = mapped_column(Text, default="", nullable=False)
    test_date: Mapped[str] = mapped_column(Text, default="", nullable=False)
    lot_no: Mapped[str] = mapped_column(Text, default="", nullable=False)
    refrigerant: Mapped[str] = mapped_column(Text, default="", nullable=False)
    refrigerant_charge: Mapped[str] = mapped_column(Text, default="", nullable=False)
    parts_spec_id: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comp: Mapped[str] = mapped_column(Text, default="", nullable=False)
    condenser: Mapped[str] = mapped_column(Text, default="", nullable=False)
    txv: Mapped[str] = mapped_column(Text, default="", nullable=False)
    hvac: Mapped[str] = mapped_column(Text, default="", nullable=False)
    pipe: Mapped[str] = mapped_column(Text, default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class SysPerfColumnMapping(Base):
    __tablename__ = "sysperf_column_mapping"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    file_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    sheet_name: Mapped[str] = mapped_column(Text, default="", nullable=False)
    original_name: Mapped[str] = mapped_column(Text, default="", nullable=False)
    standard_name: Mapped[str] = mapped_column(Text, default="", nullable=False)
    col_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SysPerfSystemConfig(Base):
    __tablename__ = "sysperf_system_config"
    __table_args__ = (
        UniqueConstraint("workspace_id", "key", name="uq_sysperf_system_config_ws_key"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_only: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# 초기 시드 — standard_columns 30개 (cycle 20 + general 10). 레거시 _init_db 와 동일.
STANDARD_COLUMNS_SEED: list[tuple[str, str, str, str, int]] = [
    ("Comp In Pressure", "PS,Ps,COMP IN,comp in pressure,흡입압력", "kgf/cm2", "cycle", 1),
    ("Comp In Temperature", "TS,Ts,COMP IN TEMP,comp in temperature,흡입온도", "℃", "cycle", 2),
    ("Comp Out Pressure", "PCO,Pd,COMP OUT,comp out pressure,토출압력", "kgf/cm2", "cycle", 3),
    ("Comp Out Temperature", "TD,Td,COMP OUT TEMP,comp out temperature,토출온도", "℃", "cycle", 4),
    ("Condenser In Pressure", "COND IN P,condenser in pressure", "kgf/cm2", "cycle", 5),
    ("Condenser In Temperature", "TCI,COND IN,condenser in temperature", "℃", "cycle", 6),
    ("Condenser Out Pressure", "COND OUT P,condenser out pressure", "kgf/cm2", "cycle", 7),
    ("Condenser Out Temperature", "TCO,COND OUT,condenser out temperature", "℃", "cycle", 8),
    ("TXV In Pressure", "TXV IN P,txv in pressure", "kgf/cm2", "cycle", 9),
    ("TXV In Temperature", "TXV IN,txv in temperature", "℃", "cycle", 10),
    ("TXV Out Pressure", "TXV OUT P,txv out pressure", "kgf/cm2", "cycle", 11),
    ("TXV Out Temperature", "TXV OUT,txv out temperature", "℃", "cycle", 12),
    ("Evap In Pressure", "EVA IN P,EVA IN PRESS,evap in pressure", "kgf/cm2", "cycle", 13),
    ("Evap In Temperature", "E/TEI,EVA IN,evap in temperature", "℃", "cycle", 14),
    ("Evap Out Pressure", "EVA OUT P,evap out pressure", "kgf/cm2", "cycle", 15),
    ("Evap Out Temperature", "E/TEO,EVA OUT,evap out temperature", "℃", "cycle", 16),
    ("Accum In Pressure", "ACCUM IN P,accum in pressure", "kgf/cm2", "cycle", 17),
    ("Accum In Temperature", "ACCUM IN,accum in temperature", "℃", "cycle", 18),
    ("Accum Out Pressure", "ACCUM OUT P,accum out pressure", "kgf/cm2", "cycle", 19),
    ("Accum Out Temperature", "ACCUM OUT,accum out temperature", "℃", "cycle", 20),
    ("Time", "TIME,time,시간,Elapsed", "min", "general", 0),
    ("Ambient Temp", "AMB,ambient,외기온,외기", "℃", "general", 101),
    ("Humidity", "HUMIDITY,humidity,습도", "%", "general", 102),
    ("Car Speed", "CARSPEED,car speed,차속", "km/h", "general", 103),
    ("Engine RPM", "ENG RPM,RPM,엔진회전수", "rpm", "general", 104),
    ("Room Avg Temp", "ROOMAVG,실내평균,room avg", "℃", "general", 105),
    ("Vent Avg Temp", "Fr VENTAVG,VENTAVG,벤트평균", "℃", "general", 106),
    ("SC Cond Out", "SC COND OUT,SC,과냉도", "℃", "general", 107),
    ("SH", "SH,과열도", "℃", "general", 108),
    ("Blower Volts", "BLWR VOLTS,블로워전압", "V", "general", 109),
]

# ── 차종 시드 (현대·기아·제네시스) 196종 — 원본 _CAR_SEED 그대로 ──
# 튜플 순서: (era, brand, year, car_name, model_code, segment_code, segment_name)
# ⚠️ INSERT 시 brand,era,year,... 순으로 재배열됨. model_code 중복 허용(UNIQUE 금지).
CAR_SEED: list[tuple[str, str, str, str, str, str, str]] = [
    # 현대 1기
    ("1", "현대", "1983", "스텔라", "Y", "F", "중형 승용"),
    ("1", "현대", "1985", "쏘나타", "Y1", "F", "중형 승용"),
    ("1", "현대", "1985", "포니엑셀/엑셀/프레스토", "X", "B/C", "소형 승용"),
    ("1", "현대", "1986", "그랜저", "L", "G", "준대형 승용"),
    ("1", "현대", "1986", "그레이스", "AH", "O/P/Q", "승합"),
    ("1", "현대", "1988", "쏘나타", "Y2", "F", "중형 승용"),
    ("1", "현대", "1989", "엑셀", "X2", "B/C", "소형 승용"),
    ("1", "현대", "1990", "스쿠프", "SLC", "K", "스포츠"),
    ("1", "현대", "1990", "엘란트라", "J", "D", "준중형 승용"),
    ("1", "현대", "1992", "그랜저/다이너스티", "LX", "G", "준대형 승용"),
    ("1", "현대", "1992", "쏘나타", "Y3", "F", "중형 승용"),
    ("1", "현대", "1994", "엑센트", "X3", "B/C", "소형 승용"),
    ("1", "현대", "1995", "마르샤", "H1", "기타", "기타"),
    ("1", "현대", "1995", "아반떼", "J2", "D", "준중형 승용"),
    ("1", "현대", "1996", "싼타모", "M2", "기타", "기타"),
    ("1", "현대", "1996", "티뷰론", "RD", "K", "스포츠"),
    ("1", "현대", "1997", "스타렉스", "A1", "O/P/Q", "승합"),
    ("1", "현대", "1998", "베르나", "LC", "B/C", "소형 승용"),
    ("1", "현대", "1998", "쏘나타", "EF", "F", "중형 승용"),
    ("1", "현대", "1998", "아토스", "MX", "기타", "기타"),
    ("1", "현대", "1998", "상트로", "MXi", "기타", "기타"),
    ("1", "현대", "1998", "그랜저", "XG", "G", "준대형 승용"),
    ("1", "현대", "1999", "에쿠스", "LZ", "I/J", "대형 승용"),
    ("1", "현대", "1999", "트라제 XG", "FO", "O/P/Q", "승합"),
    ("1", "현대", "2000", "아반떼", "XD", "D", "준중형 승용"),
    ("1", "현대", "2000", "싼타페", "SM", "M", "중형 SUV"),
    ("1", "현대", "2001", "투스카니", "GK", "K", "스포츠"),
    ("1", "현대", "2001", "테라칸", "HP", "N", "준대형 SUV"),
    ("1", "현대", "2001", "라비타/매트릭스", "FC", "B/C", "소형 승용"),
    ("1", "현대", "2002", "클릭", "TB", "B/C", "소형 승용"),
    ("1", "현대", "2004", "쏘나타", "NF", "F", "중형 승용"),
    ("1", "현대", "2004", "투싼", "JM", "L", "준중형 SUV"),
    ("1", "현대", "2005", "그랜저", "TG", "G", "준대형 승용"),
    ("1", "현대", "2005", "베르나", "MC", "B/C", "소형 승용"),
    ("1", "현대", "2006", "아반떼", "HD", "D", "준중형 승용"),
    ("1", "현대", "2006", "베라크루즈", "EN", "N", "준대형 SUV"),
    ("1", "현대", "2007", "스타렉스", "TQ", "O/P/Q", "승합"),
    ("1", "현대", "2007", "i30", "FD", "D", "준중형 승용"),
    ("1", "현대", "2008", "i10", "PA", "A", "경형"),
    ("1", "현대", "2008", "i20", "PB", "B/C", "소형 승용"),
    ("1", "현대", "2008", "제네시스 쿠페", "BK", "K", "스포츠"),
    ("1", "현대", "2008", "위에둥", "HDC", "D", "준중형 승용"),
    ("1", "현대", "2009", "쏘나타", "YF", "F", "중형 승용"),
    ("1", "현대", "2010", "아반떼", "MD", "D", "준중형 승용"),
    ("1", "현대", "2010", "엑센트", "RB", "B/C", "소형 승용"),
    ("1", "현대", "2010", "그랜저", "HG", "G", "준대형 승용"),
    ("1", "현대", "2010", "에쿠스", "VI", "I/J", "대형 승용"),
    ("1", "현대", "2010", "싼타페", "CM", "M", "중형 SUV"),
    ("1", "현대", "2010", "투싼/ix35", "LM", "L", "준중형 SUV"),
    ("1", "현대", "2010", "ix35", "LM", "L", "준중형 SUV"),
    ("1", "현대", "2010", "블루온", "PA", "A", "경형"),
    ("1", "현대", "2010", "ix20", "JC", "B/C", "소형 승용"),
    ("1", "현대", "2011", "이온", "HA", "A", "경형"),
    ("1", "현대", "2011", "i30", "GD", "D", "준중형 승용"),
    ("1", "현대", "2011", "벨로스터", "FS", "S", "소형 SUV"),
    ("1", "현대", "2011", "i40", "VF", "F", "중형 승용"),
    ("1", "현대", "2012", "싼타페", "DM", "M", "중형 SUV"),
    ("1", "현대", "2012", "아반떼 쿠페", "JK", "K", "스포츠"),
    ("1", "현대", "2012", "HB20", "HB", "B/C", "소형 승용"),
    ("1", "현대", "2013", "i10", "BA/IA", "A", "경형"),
    ("1", "현대", "2013", "맥스크루즈", "NC", "N", "준대형 SUV"),
    ("1", "현대", "2014", "아슬란", "AG", "G", "준대형 승용"),
    ("1", "현대", "2014", "i20", "GB", "B/C", "소형 승용"),
    ("1", "현대", "2014", "ix25/크레타", "GC/GS", "S", "소형 SUV"),
    ("1", "현대", "2014", "쏘나타", "LF", "F", "중형 승용"),
    ("1", "현대", "2015", "아반떼", "AD", "D", "준중형 승용"),
    ("1", "현대", "2015", "투싼", "TL", "L", "준중형 SUV"),
    ("1", "현대", "2016", "그랜저", "IG", "G", "준대형 승용"),
    ("1", "현대", "2016", "엑센트", "YC", "B/C", "소형 승용"),
    ("1", "현대", "2016", "아이오닉", "AE", "E", "친환경"),
    ("1", "현대", "2017", "솔라리스", "HC", "B/C", "소형 승용"),
    ("1", "현대", "2017", "루이나", "RC", "B/C", "소형 승용"),
    ("1", "현대", "2017", "코나", "OS", "S", "소형 SUV"),
    ("1", "현대", "2017", "ix35", "NU", "L", "준중형 SUV"),
    ("1", "현대", "2017", "위에둥/첼레스타", "ID", "D", "준중형 승용"),
    ("1", "현대", "2018", "넥쏘", "FE", "E", "친환경"),
    ("1", "현대", "2018", "싼타페", "TM", "M", "중형 SUV"),
    ("1", "현대", "2018", "벨로스터", "JS", "S", "소형 SUV"),
    ("1", "현대", "2018", "라페스타", "SQ", "기타", "기타"),
    ("1", "현대", "2019", "i10", "AC3", "A", "경형"),
    ("1", "현대", "2019", "그랜드 i10", "AI3", "A", "경형"),
    ("1", "현대", "2019", "팰리세이드", "LX2", "N", "준대형 SUV"),
    ("1", "현대", "2019", "ix25", "SU2", "S", "소형 SUV"),
    # 기아 1기
    ("1", "기아", "1987", "프라이드", "Y", "B/C", "소형 승용"),
    ("1", "기아", "1991", "갤로퍼", "M-CAR/M1", "기타", "기타"),
    ("1", "기아", "1992", "포텐샤", "T", "기타", "기타"),
    ("1", "기아", "1993", "스포티지", "NB-7", "L", "준중형 SUV"),
    ("1", "기아", "1994", "아벨라", "WB", "B/C", "소형 승용"),
    ("1", "기아", "1995", "크레도스", "G", "F", "중형 승용"),
    ("1", "기아", "1996", "씨드", "ED", "D", "준중형 승용"),
    ("1", "기아", "1996", "세피아", "S2", "D", "준중형 승용"),
    ("1", "기아", "1997", "엔터프라이즈", "T3", "기타", "기타"),
    ("1", "기아", "1998", "카니발", "GQ", "O/P/Q", "승합"),
    ("1", "기아", "1998", "크레도스", "G2", "F", "중형 승용"),
    ("1", "기아", "1998", "비스토", "MXL", "기타", "기타"),
    ("1", "기아", "1999", "리오", "BC", "B/C", "소형 승용"),
    ("1", "기아", "1999", "카렌스", "RS", "O/P/Q", "승합"),
    ("1", "기아", "2000", "스펙트라", "SD", "D", "준중형 승용"),
    ("1", "기아", "2000", "옵티마", "MS", "F", "중형 승용"),
    ("1", "기아", "2002", "쏘렌토", "BL", "M", "중형 SUV"),
    ("1", "기아", "2003", "쎄라토", "LD", "D", "준중형 승용"),
    ("1", "기아", "2003", "오피러스", "GH", "H", "준대형 럭셔리"),
    ("1", "기아", "2004", "스포티지", "KM", "L", "준중형 SUV"),
    ("1", "기아", "2005", "프라이드", "JB", "B/C", "소형 승용"),
    ("1", "기아", "2005", "로체", "MG", "F", "중형 승용"),
    ("1", "기아", "2005", "카니발/앙투라", "VQ", "O/P/Q", "승합"),
    ("1", "기아", "2006", "씨드/프로씨드", "JD", "D", "준중형 승용"),
    ("1", "기아", "2006", "카렌스", "UN", "O/P/Q", "승합"),
    ("1", "기아", "2008", "포르테", "TD", "D", "준중형 승용"),
    ("1", "기아", "2008", "모하비", "HM", "N", "준대형 SUV"),
    ("1", "기아", "2008", "쏘울", "AM", "S", "소형 SUV"),
    ("1", "기아", "2009", "K7", "VG", "G", "준대형 승용"),
    ("1", "기아", "2009", "쏘렌토", "XM", "M", "중형 SUV"),
    ("1", "기아", "2009", "벤가", "YN", "B/C", "소형 승용"),
    ("1", "기아", "2009", "포르테 쿱", "XK", "K", "스포츠"),
    ("1", "기아", "2010", "K5", "TF", "F", "중형 승용"),
    ("1", "기아", "2010", "스포티지", "SL", "L", "준중형 SUV"),
    ("1", "기아", "2011", "프라이드", "UB", "B/C", "소형 승용"),
    ("1", "기아", "2011", "프라이드(북미형)", "LB", "B/C", "소형 승용"),
    ("1", "기아", "2011", "K2", "QB", "B/C", "소형 승용"),
    ("1", "기아", "2011", "모닝", "TA", "A", "경형"),
    ("1", "기아", "2011", "레이", "TAM", "A", "경형"),
    ("1", "기아", "2012", "K3", "YD", "D", "준중형 승용"),
    ("1", "기아", "2012", "K9", "KH", "I/J", "대형 승용"),
    ("1", "기아", "2013", "쏘울", "PS", "S", "소형 SUV"),
    ("1", "기아", "2013", "K3 쿱", "YK", "K", "스포츠"),
    ("1", "기아", "2013", "카렌스", "RP", "O/P/Q", "승합"),
    ("1", "기아", "2014", "쏘렌토", "UM", "M", "중형 SUV"),
    ("1", "기아", "2014", "카니발", "YP", "O/P/Q", "승합"),
    ("1", "기아", "2014", "K4", "PF", "F", "중형 승용"),
    ("1", "기아", "2015", "K5", "JF", "F", "중형 승용"),
    ("1", "기아", "2015", "스포티지", "QL", "L", "준중형 SUV"),
    ("1", "기아", "2015", "KX3", "KC", "S", "소형 SUV"),
    ("1", "기아", "2016", "K7", "YG", "G", "준대형 승용"),
    ("1", "기아", "2016", "K2", "UC", "B/C", "소형 승용"),
    ("1", "기아", "2016", "리오", "YB/FB/UC", "B/C", "소형 승용"),
    ("1", "기아", "2016", "스토닉", "YB CUV", "B/C", "소형 승용"),
    ("1", "기아", "2016", "씨드/프로씨드/엑씨드", "CD", "D", "준중형 승용"),
    ("1", "기아", "2016", "니로", "DE", "E", "친환경"),
    ("1", "기아", "2016", "KX7", "QM", "M", "중형 SUV"),
    ("1", "기아", "2017", "모닝", "JA", "A", "경형"),
    ("1", "기아", "2017", "스팅어", "CK", "K", "스포츠"),
    ("1", "기아", "2017", "페가스", "AB", "B/C", "소형 승용"),
    ("1", "기아", "2018", "K3", "BD", "D", "준중형 승용"),
    ("1", "기아", "2018", "KX1/이파오", "QE", "B/C", "소형 승용"),
    ("1", "기아", "2018", "즈파오", "NP", "기타", "기타"),
    ("1", "기아", "2019", "K5", "DL3", "F", "중형 승용"),
    ("1", "기아", "2019", "셀토스", "SP2", "S", "소형 SUV"),
    ("1", "기아", "2019", "텔루라이드", "ON", "N", "준대형 SUV"),
    ("1", "기아", "2019", "쏘울", "SK3", "S", "소형 SUV"),
    ("1", "기아", "2020", "쏘렌토", "MQ4", "M", "중형 SUV"),
    ("1", "기아", "2020", "카니발", "KA4", "O/P/Q", "승합"),
    # 제네시스 1기
    ("1", "제네시스", "2008", "제네시스", "BH", "H", "준대형 럭셔리"),
    ("1", "제네시스", "2013", "제네시스/G80", "DH", "H", "준대형 럭셔리"),
    ("1", "제네시스", "2015", "EQ900", "HI", "I/J", "대형 승용"),
    ("1", "제네시스", "2017", "G70", "IK", "K", "스포츠"),
    ("1", "제네시스", "2018", "G90", "HI", "I/J", "대형 승용"),
    ("1", "제네시스", "2018", "K9", "RJ", "I/J", "대형 승용"),
    # 현대 2기
    ("2", "현대", "2018", "쌍트로", "AH2", "A", "경형"),
    ("2", "현대", "2019", "i10", "AC3", "A", "경형"),
    ("2", "현대", "2019", "그랜드 i10/아우라", "AI3", "A", "경형"),
    ("2", "현대", "2019", "팰리세이드", "LX2", "L", "준대형 SUV"),
    ("2", "현대", "2019", "ix25", "SU2", "S", "소형 SUV"),
    ("2", "현대", "2019", "HB20", "BR2", "B", "소형 승용"),
    ("2", "현대", "2019", "베뉴", "QX1", "Q", "초소형 SUV"),
    ("2", "현대", "2020", "i20", "BC3/BI3", "B", "소형 승용"),
    ("2", "현대", "2020", "아반떼", "CN7", "C", "준중형 승용"),
    ("2", "현대", "2020", "쏘나타", "DN8", "D", "중형 승용"),
    ("2", "현대", "2020", "투싼", "NX4", "N", "준중형 SUV"),
    ("2", "현대", "2020", "크레타", "SU2", "S", "소형 SUV"),
    ("2", "현대", "2020", "G80", "RG3", "G", "준대형 승용"),
    ("2", "현대", "2021", "캐스퍼", "AX1", "A", "경형"),
    ("2", "현대", "2021", "바이욘", "BC3 CUV", "B", "소형 승용"),
    ("2", "현대", "2021", "아이오닉 5", "NE1", "N", "준중형 SUV"),
    ("2", "현대", "2021", "싼타크루즈", "NX4A OB", "N", "준중형 SUV"),
    ("2", "현대", "2021", "쿠스토", "KU1", "K", "MPV"),
    ("2", "현대", "2021", "스타리아", "US4", "U", "상용"),
    ("2", "현대", "2021", "미스트라", "DU2", "D", "중형 승용"),
    ("2", "현대", "2022", "아이오닉 6", "CE1", "C", "준중형 승용"),
    ("2", "현대", "2022", "그랜저", "GN7", "G", "준대형 승용"),
    ("2", "현대", "2022", "스타게이저", "KS1", "K", "MPV"),
    ("2", "현대", "2022", "ix35", "NU2", "N", "준중형 SUV"),
    ("2", "현대", "2023", "엑센트", "BN7", "B", "소형 승용"),
    ("2", "현대", "2023", "싼타페", "MX5", "M", "중형 SUV"),
    ("2", "현대", "2023", "코나", "SX2", "S", "소형 SUV"),
    ("2", "현대", "2025", "팰리세이드", "LX3", "L", "준대형 SUV"),
    ("2", "현대", "2025", "아이오닉 9", "ME1", "M", "중형 SUV"),
    # 기아 2기
    ("2", "기아", "2019", "쏘울", "SK3", "S", "소형 SUV"),
    ("2", "기아", "2019", "셀토스", "SP2", "S", "소형 SUV"),
    ("2", "기아", "2020", "카니발", "KA4", "K", "MPV"),
    ("2", "기아", "2020", "쏘렌토", "MQ4", "M", "중형 SUV"),
    ("2", "기아", "2020", "쏘넷", "QY1", "Q", "초소형 SUV"),
    ("2", "기아", "2021", "스포티지", "NQ5", "N", "준중형 SUV"),
    ("2", "기아", "2021", "EV6", "CV1", "C", "준중형 승용"),
    ("2", "기아", "2021", "니로", "SG2", "S", "소형 SUV"),
    ("2", "기아", "2022", "카렌스", "KY1", "K", "MPV"),
    ("2", "기아", "2023", "K3", "BL7", "B", "소형 승용"),
    ("2", "기아", "2023", "EV9", "MV1", "M", "중형 SUV"),
    ("2", "기아", "2023", "EV5", "OV1", "O", "준중형 SUV"),
    ("2", "기아", "2024", "K4", "CL4", "C", "준중형 승용"),
    ("2", "기아", "2024", "EV3", "SV1", "S", "소형 SUV"),
    ("2", "기아", "2025", "셀토스", "SP3", "S", "소형 SUV"),
    ("2", "기아", "2025", "EV4", "CT1", "C", "준중형 승용"),
    ("2", "기아", "2025", "타스만", "TK1", "T", "픽업트럭"),
    ("2", "기아", "2025", "시로스", "AY1", "A", "경형"),
    # 제네시스 2기
    ("2", "제네시스", "2020", "GV80", "JX1", "X", "준대형 SUV"),
    ("2", "제네시스", "2020", "GV70", "JK1", "K", "중형 SUV"),
    ("2", "제네시스", "2020", "G80", "RG3", "G", "준대형 승용"),
    ("2", "제네시스", "2021", "GV60", "JW1", "W", "준중형 SUV"),
    ("2", "제네시스", "2021", "G90", "RS4", "S", "대형 승용"),
]
