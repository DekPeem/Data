"""พยากรณ์ "รูปทรง" เส้นโค้งการใช้ไฟรายชั่วโมง (P / OP / H) จากตัวเลขบนบิลค่าไฟเท่านั้น — สำหรับ
ผู้ใช้ไฟที่ยังไม่มี AMR (ไม่มีข้อมูลรายช่วงเวลา 15 นาทีจริงเลย) มีแค่ตัวเลขที่พิมพ์บนบิลปกติ:
    - กำลังไฟฟ้าสูงสุด (Peak demand, kW) ของแต่ละช่วง P/OP/H
    - หน่วยไฟที่ใช้ (Energy, kWh) ของแต่ละช่วง P/OP/H

พอร์ตมาจากสคริปต์ CLI แบบ standalone (forecast_load.py — วิ่งด้วย matplotlib/numpy ในเครื่องผู้ใช้
เอง) ตัดส่วน argparse/CLI + ฟีเจอร์ --calibrate (เรียนรู้รูปทรงใหม่จากไฟล์ AMR จริง) ออก เหลือแค่
ฟังก์ชันล้วนๆ ให้ web/app.py เรียกใช้ตรงๆ — ยังใช้ค่า TEMPLATE_WEEKDAY/TEMPLATE_HOLIDAY เดิม
(เรียนรู้จากข้อมูล AMR จริง 12 เดือนของโรงงาน TOU รายหนึ่งไว้แล้วตั้งแต่ต้นฉบับ) เป็นรูปทรงตั้งต้น
เสมอ ไม่มีทางเลือกอัปโหลดไฟล์ AMR มาปรับรูปทรงเองในเว็บนี้ (ยังไม่ทำ — ถ้าต้องการค่อยเพิ่มทีหลัง)

⚠️ นี่คือ "รูปทรงที่สร้างขึ้นให้ดูสมเหตุสมผล" ไม่ใช่การวัดจริง — ยิงให้ตรง Peak ที่กรอกมาเป๊ะที่ชั่วโมง
ที่มักเป็น Peak จริง (ตามรูปทรงต้นแบบ) และเฉลี่ยรวมให้ตรงกับหน่วยไฟที่กรอกมา พร้อมมีรอยบุ๋มช่วงเที่ยง
ตามเปอร์เซ็นต์ที่กำหนด — ไม่ได้อิงข้อมูลจริงของบริษัทอื่นในระบบเหมือนโมเดลเดิมที่เคยมีก่อนถูกตัดออก
(ดู git history ของ src/amr_mapping/mapping.py ถ้าอยากดูของเก่า)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")  # เซิร์ฟเวอร์ไม่มีจอแสดงผล — ต้องตั้งก่อน import pyplot เสมอ

import numpy as np

COLORS = {"P": "#eb6834", "OP": "#1baf7a", "H": "#6250d6"}
RED = "#e34948"
THAI_FONTS = ["Noto Sans Thai", "Sarabun", "TH Sarabun New", "Tahoma", "Leelawadee UI", "Thonburi"]

P_HOURS = list(range(9, 22))
OP_HOURS = [h for h in range(24) if h not in P_HOURS]

# รูปทรงตั้งต้น (relative shape เท่านั้น — ถูกสเกลใหม่ให้ตรง Peak/หน่วยไฟที่กรอกมาเสมอ) เรียนรู้จาก
# ข้อมูล AMR จริง 12 เดือนของโรงงาน TOU รายหนึ่ง (วันทำการ P+OP รวมกัน, วันหยุดเฉพาะวันที่เดินเครื่อง)
TEMPLATE_WEEKDAY = [394, 388, 372, 358, 362, 368, 352, 380, 480, 424, 370, 326,
                    198, 369, 420, 486, 530, 437, 560, 564, 523, 440, 434, 414]
TEMPLATE_HOLIDAY = [414, 407, 388, 374, 375, 368, 346, 342, 428, 362, 299, 270,
                     152, 296, 349, 417, 448, 357, 415, 413, 376, 352, 348, 339]

DEFAULT_DAYS = {"P": 22, "OP": 22, "H": 8}
DEFAULT_LUNCH_DROP_PCT = 43.0


def _shape_for(hours: List[int], template: List[int]) -> np.ndarray:
    vals = np.array([template[h] for h in hours], dtype=float)
    return vals / vals.max()  # 1.0 ที่ชั่วโมง peak ของ segment นั้น


def _gamma_curve(shape: np.ndarray, peak: float, gamma: float) -> np.ndarray:
    return peak * np.power(shape, gamma)


def _solve_gamma(shape: np.ndarray, peak: float, target_avg: float) -> float:
    """หาค่า gamma ที่ทำให้ mean(peak * shape**gamma) == target_avg (bisection)"""

    if target_avg >= peak:
        return 0.0  # แบนที่สุดที่ยอมได้ — ค่าเฉลี่ยเกิน peak ไปไม่ได้ด้วยรูปทรงนี้
    lo, hi = 0.0, 40.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if _gamma_curve(shape, peak, mid).mean() > target_avg:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def build_curve(
    hours: List[int],
    template: List[int],
    peak: float,
    energy_kwh: float,
    days: int,
    drop_pct: float,
    lunch_hours: Tuple[int, ...] = (12,),
) -> Dict[int, float]:
    """คืน dict ชั่วโมง -> kW ของ segment เดียว (P หรือ OP หรือ H)"""

    n_hours = len(hours)
    if days <= 0 or n_hours == 0:
        return {h: 0.0 for h in hours}
    target_avg = energy_kwh / (days * n_hours)
    target_avg = min(target_avg, peak)  # ค่าเฉลี่ยเกิน peak ไปไม่ได้

    shape = _shape_for(hours, template)
    gamma = _solve_gamma(shape, peak, target_avg)
    curve = _gamma_curve(shape, peak, gamma)
    result = dict(zip(hours, curve))
    peak_hour = hours[int(np.argmax(shape))]

    # ใส่/บังคับรอยบุ๋มช่วงเที่ยง แล้วกระจายพลังงานที่ตัดออกไปคืนให้ชั่วโมงอื่น (ไม่รวมชั่วโมง peak)
    # เพื่อให้ค่าเฉลี่ยรวมยังตรงกับที่กำหนดไว้เหมือนเดิม
    lh = [h for h in lunch_hours if h in result and h != peak_hour]
    if lh and drop_pct > 0:
        others = [h for h in hours if h not in lh and h != peak_hour]
        neighbor_ref = np.mean([result[h] for h in others]) if others else result[hours[0]]
        for h in lh:
            new_val = neighbor_ref * (1 - drop_pct / 100)
            delta = result[h] - new_val
            result[h] = max(0.0, new_val)
            if others:
                weights = np.array([result[o] for o in others])
                weights = weights / weights.sum() if weights.sum() > 0 else np.ones(len(others)) / len(others)
                for o, w in zip(others, weights):
                    result[o] = min(peak, result[o] + delta * w)
    return result


def _setup_font() -> bool:
    from matplotlib import font_manager as fm

    names = {f.name for f in fm.fontManager.ttflist}
    for n in THAI_FONTS:
        if n in names:
            matplotlib.rcParams["font.family"] = n
            return True
    return False


BG = "#FAFAFA"  # สีพื้นหลังของแต่ละ panel
GRID = "#FFFFFF"  # สีเส้น gridline (โผล่เป็นเส้นจางๆ บนพื้นสีเทาอ่อน)
LINE = "#333333"  # สีเส้น/จุดที่ลากต่อยอดแท่งกราฟ


def _rounded_bar(ax, x: float, height: float, width: float, color: str, alpha: float = 0.88) -> None:
    """แท่งกราฟมุมมนด้านบน (ฐานเรียบ) — สวยกว่า ax.bar() เหลี่ยมธรรมดา (ต้นฉบับ forecast_load.py
    เวอร์ชันล่าสุดของผู้ใช้ใช้แบบนี้ ดู README/git history ของสคริปต์นั้นถ้าอยากดูเทียบ)"""

    from matplotlib.patches import FancyBboxPatch

    if height <= 0:
        return
    ax.add_patch(FancyBboxPatch(
        (x - width / 2, 0), width, height,
        boxstyle=f"round,pad=0,rounding_size={width * 0.16}",
        linewidth=0, facecolor=color, alpha=alpha, mutation_aspect=1, zorder=3,
    ))


def draw(curve_wd: Dict[int, float], curve_h: Dict[int, float], peaks: Dict[str, float]):
    """คืน matplotlib Figure — วาดเฉพาะ panel ที่มีข้อมูลจริง (ข้าม weekday panel ถ้าไม่มีทั้ง P/OP,
    ข้าม holiday panel ถ้าไม่มี H — ต่างจาก forecast_load.py ต้นฉบับที่วาดทั้ง 2 panel เสมอ เพราะเว็บนี้
    รองรับกรอกแค่บางช่วง P/OP/H ก็พยากรณ์ได้ ถ้าวาดครบ 2 panel เสมอจะ error ตอนหา peaks[r] ของช่วง
    ที่ไม่ได้กรอกมา) เลือกภาษาไทย/อังกฤษของข้อความในกราฟเองตามฟอนต์ที่มีอยู่จริงบนเซิร์ฟเวอร์ (กัน
    ตัวอักษรไทยกลายเป็นกล่องว่างถ้าเซิร์ฟเวอร์ไม่มีฟอนต์ไทยติดตั้งไว้)"""

    import matplotlib.pyplot as plt

    thai = _setup_font()
    title = "พยากรณ์รูปทรงการใช้ไฟ (ไม่มี AMR)" if thai else "Forecast load shape (no-AMR estimate)"
    L = dict(
        wd="วันทำการ (OP + P) - คาดการณ์" if thai else "Weekday (OP + P) - forecast",
        hd="วันหยุด (H) - คาดการณ์" if thai else "Holiday (H) - forecast",
        hour="ชั่วโมงของวัน" if thai else "Hour of day",
        peak="Peak",
    )
    ymax = max(peaks.values()) * 1.28

    panels = []
    if curve_wd:
        panels.append((curve_wd, lambda h: "P" if 9 <= h < 22 else "OP",
                        [(0, 9, "OP"), (9, 22, "P"), (22, 24, "OP")], L["wd"]))
    if curve_h:
        panels.append((curve_h, lambda h: "H", [(0, 24, "H")], L["hd"]))

    fig, axes = plt.subplots(len(panels), 1, figsize=(12, 4.5 * len(panels)), facecolor="white", squeeze=False)
    axes = axes[:, 0]

    def panel(ax, curve, rate_of, segs, name):
        ax.set_facecolor(BG)
        xs = np.arange(24)
        ys = np.array([curve.get(h, 0) for h in range(24)], dtype=float)
        width = 0.64
        for h in range(24):
            _rounded_bar(ax, h, ys[h], width, COLORS[rate_of(h)])
        ax.plot(xs, ys, color=LINE, linewidth=1.3, alpha=0.55, zorder=4)
        ax.scatter(xs, ys, color=LINE, s=15, zorder=5, linewidths=0)

        for a, b, r in segs:
            if r not in peaks:
                continue
            pk = peaks[r]
            ax.hlines(pk, a, b, colors=COLORS[r], linestyles=(0, (5, 3)), linewidth=2, zorder=2)
            if b - a >= 4:
                ax.annotate(
                    f"{L['peak']} {r}: {pk:,.0f} kW", ((a + b) / 2, pk),
                    xytext=(0, 10), textcoords="offset points", ha="center",
                    fontsize=10.5, fontweight="bold", color="#222", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=COLORS[r], lw=1.3),
                )

        ax.set_title(name, loc="left", fontsize=13, fontweight="bold", color="#222", pad=14)
        ax.set_xlim(-0.6, 23.6)
        ax.set_ylim(0, ymax)
        ax.set_xticks(range(0, 24, 3))
        ax.set_ylabel("kW", fontsize=10, color="#555")
        ax.grid(axis="y", color=GRID, linewidth=1.6, zorder=0)
        ax.set_axisbelow(True)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.tick_params(colors="#777", labelsize=9.5)

    for ax, (curve, rate_of, segs, name) in zip(axes, panels):
        panel(ax, curve, rate_of, segs, name)
    axes[-1].set_xlabel(L["hour"], fontsize=10, color="#555")

    fig.suptitle(title, fontsize=15, fontweight="bold", color="#111", y=0.995)
    fig.text(
        0.01, 0.005,
        "Forecast shape only - not a measurement. Built from Peak + energy (kWh) + lunch-dip %.",
        fontsize=8, color="#999",
    )
    fig.tight_layout(rect=(0, 0.02, 1, 0.965), h_pad=3.5)
    return fig


def render_png(fig) -> bytes:
    """เขียน Figure เป็น PNG bytes แล้วปิด figure ทิ้งเสมอ (กัน memory leak ตอนรันเป็นเซิร์ฟเวอร์
    ระยะยาว — matplotlib ไม่ปิด figure ให้อัตโนมัติ)"""

    import io

    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=140)
    finally:
        plt.close(fig)
    return buf.getvalue()


def forecast_shape_png(
    *,
    peak_p: Optional[float] = None,
    energy_p: Optional[float] = None,
    days_p: Optional[int] = None,
    peak_op: Optional[float] = None,
    energy_op: Optional[float] = None,
    days_op: Optional[int] = None,
    peak_h: Optional[float] = None,
    energy_h: Optional[float] = None,
    days_h: Optional[int] = None,
    drop_pct: float = DEFAULT_LUNCH_DROP_PCT,
) -> bytes:
    """สร้างกราฟพยากรณ์เส้นโค้ง PNG จากพารามิเตอร์ระดับบิล — ต้องมีอย่างน้อย 1 คู่ peak+energy
    (P, OP หรือ H) raise ValueError ถ้าไม่มีเลยสักคู่ ช่วงที่ไม่ได้กรอก (peak<=0 หรือไม่ส่งมา) จะถูก
    ข้ามไปเฉยๆ ไม่ error"""

    curve_wd: Dict[int, float] = {}
    curve_h: Dict[int, float] = {}
    peaks: Dict[str, float] = {}

    segments = [
        ("P", P_HOURS, TEMPLATE_WEEKDAY, peak_p, energy_p, days_p or DEFAULT_DAYS["P"], (12,), curve_wd),
        ("OP", OP_HOURS, TEMPLATE_WEEKDAY, peak_op, energy_op, days_op or DEFAULT_DAYS["OP"], (), curve_wd),
        ("H", list(range(24)), TEMPLATE_HOLIDAY, peak_h, energy_h, days_h or DEFAULT_DAYS["H"], (12,), curve_h),
    ]
    for rate, hours, template, peak, energy, days, lunch, dest in segments:
        if not peak or peak <= 0:
            continue
        dest.update(build_curve(hours, template, peak, energy or 0.0, days, drop_pct, lunch))
        peaks[rate] = peak

    if not peaks:
        raise ValueError("ต้องกรอก Peak อย่างน้อย 1 ช่วง (P, OP หรือ H)")

    fig = draw(curve_wd, curve_h, peaks)
    return render_png(fig)
