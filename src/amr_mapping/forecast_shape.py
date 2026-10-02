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


# กล่อง (Q1-Q3) / whisker ของ box-and-whisker เป็นแค่ "ช่วงสมมติ" รอบเส้นโค้งที่พยากรณ์ไว้เท่านั้น
# (ข้อมูลตรงนี้มีแค่ 1 ค่าต่อชั่วโมง ไม่มีการกระจายตัวจริงให้คำนวณ Q1/Q3 ได้) ผู้ใช้ยืนยันอยากให้
# กราฟหน้าตาเป็นกล่อง Boxplot จริงเหมือน amr_boxplot.render_boxplot_png ไม่ใช่แค่ปรับสี — ใช้ตัวเลข
# เหล่านี้สร้างกล่องขึ้นมาล้วนๆ ต้องติดป้ายบนกราฟเสมอว่าเป็นช่วงสมมติ กันเข้าใจผิดว่าเป็นค่าแปรปรวน
# ที่วัดได้จริง
BOX_SPREAD_PCT = 0.10
WHISKER_SPREAD_PCT = 0.15


def _synthetic_box_stats(curve: Dict[int, float], ceiling_by_hour: Dict[int, float]) -> List[dict]:
    """สร้างค่าสถิติ box-and-whisker สมมติต่อชั่วโมง จากเส้นโค้งพยากรณ์ (เส้นกลาง/median = ค่าที่
    พยากรณ์ไว้เป๊ะ, กล่อง = ±BOX_SPREAD_PCT, whisker = ±WHISKER_SPREAD_PCT) รูปแบบ dict เดียวกับ
    matplotlib bxp ที่ amr_boxplot._box_stats ใช้ ไม่มี fliers เพราะไม่มีข้อมูลจริงให้หา outlier

    ceiling_by_hour (ชั่วโมง -> ค่า Peak ที่ผู้ใช้ประกาศไว้ของ rate ชั่วโมงนั้น) ใช้ clamp ขอบบนของ
    กล่อง/whisker ไม่ให้เกิน Peak ที่ประกาศไว้เด็ดขาด — ไม่งั้นที่ชั่วโมง peak เอง (median == peak
    พอดี) ส่วนบนของ box/whisker จะทะลุเส้นประ "Peak" ที่วาดกำกับไว้ ดูขัดแย้งกันเอง (เส้น Peak ควร
    เป็นเพดานสูงสุดที่ไม่มีอะไรเกินได้) ขอบล่างไม่ clamp เพราะมีแต่ 0 เป็นขอบเขตอยู่แล้ว"""

    out = []
    for h in range(24):
        v = curve.get(h, 0.0)
        ceiling = ceiling_by_hour.get(h, v)
        out.append(dict(
            med=v,
            q1=v * (1 - BOX_SPREAD_PCT),
            q3=min(ceiling, v * (1 + BOX_SPREAD_PCT)),
            whislo=max(0.0, v * (1 - WHISKER_SPREAD_PCT)),
            whishi=min(ceiling, v * (1 + WHISKER_SPREAD_PCT)),
            fliers=[],
        ))
    return out


def draw(curve_wd: Dict[int, float], curve_h: Dict[int, float], peaks: Dict[str, float], bill_total: Optional[float] = None):
    """คืน matplotlib Figure — วาดเฉพาะ panel ที่มีข้อมูลจริง (ข้าม weekday panel ถ้าไม่มีทั้ง P/OP,
    ข้าม holiday panel ถ้าไม่มี H — ต่างจาก forecast_load.py ต้นฉบับที่วาดทั้ง 2 panel เสมอ เพราะเว็บนี้
    รองรับกรอกแค่บางช่วง P/OP/H ก็พยากรณ์ได้ ถ้าวาดครบ 2 panel เสมอจะ error ตอนหา peaks[r] ของช่วง
    ที่ไม่ได้กรอกมา) เลือกภาษาไทย/อังกฤษของข้อความในกราฟเองตามฟอนต์ที่มีอยู่จริงบนเซิร์ฟเวอร์ (กัน
    ตัวอักษรไทยกลายเป็นกล่องว่างถ้าเซิร์ฟเวอร์ไม่มีฟอนต์ไทยติดตั้งไว้)

    วาดเป็นกล่อง box-and-whisker แบบเดียวกับ render_boxplot_png ใน amr_boxplot.py ทุกจุด (สี/
    พื้นหลัง/กริด/เส้นขอบ/ขนาดฟอนต์หัวเรื่อง) ให้กราฟ 2 แบบในระบบเป็นตระกูลเดียวกัน — ต่างกันแค่ว่า
    กล่อง/whisker ตรงนี้เป็น "ช่วงสมมติ" ที่สร้างขึ้นรอบเส้นโค้งที่พยากรณ์ไว้เท่านั้น (ดู
    _synthetic_box_stats) เพราะข้อมูลมีแค่ 1 ค่าต่อชั่วโมง ไม่มีการกระจายตัวจริงให้คำนวณ Q1-Q3 ได้
    เหมือน amr_boxplot ที่ใช้ข้อมูล AMR จริงหลายวัน — ต้องติดป้ายกำกับบนกราฟเสมอว่าเป็นช่วงสมมติ

    bill_total (ไม่บังคับ) ใส่ยอดเงินรวมตามบิลจริงได้ แสดงกำกับเป็นข้อความอ้างอิงใต้หัวเรื่องเฉยๆ
    (ไม่ได้เอาไปคำนวณอะไรเลย — เหตุผลเดียวกับ subtitle บัญชี/บริษัทใน amr_boxplot.render_boxplot_png
    ไม่ต้องกะด้วยตาว่าบิลใบไหนตรงกับกราฟไหน)"""

    import matplotlib.pyplot as plt

    thai = _setup_font()
    title = "พยากรณ์รูปทรงการใช้ไฟ (ไม่มี AMR)" if thai else "Forecast load shape (no-AMR estimate)"
    if bill_total is not None:
        bill_line = (
            f"ยอดเงินตามบิล: {bill_total:,.2f} บาท (ข้อมูลอ้างอิง ไม่ได้ใช้คำนวณ)"
            if thai else f"Bill total: {bill_total:,.2f} THB (reference only, not used in the forecast)"
        )
        title = f"{title}\n{bill_line}"
    L = dict(
        wd="วันทำการ (OP + P) - คาดการณ์" if thai else "Weekday (OP + P) - forecast",
        hd="วันหยุด (H) - คาดการณ์" if thai else "Holiday (H) - forecast",
        hour="ชั่วโมงของวัน" if thai else "Hour of day",
        peak="Peak",
    )
    ymax = max(peaks.values()) * (1 + WHISKER_SPREAD_PCT) * 1.15  # เผื่อที่ whisker บนสุด + ป้าย Peak

    panels = []
    if curve_wd:
        panels.append((curve_wd, lambda h: "P" if 9 <= h < 22 else "OP",
                        [(0, 9, "OP"), (9, 22, "P"), (22, 24, "OP")], L["wd"]))
    if curve_h:
        panels.append((curve_h, lambda h: "H", [(0, 24, "H")], L["hd"]))

    fig, axes = plt.subplots(len(panels), 1, figsize=(12, 4.5 * len(panels)), facecolor="white", squeeze=False)
    axes = axes[:, 0]

    def panel(ax, curve, rate_of, segs, name):
        ceiling_by_hour = {h: peaks[rate_of(h)] for h in range(24) if rate_of(h) in peaks}
        stats = _synthetic_box_stats(curve, ceiling_by_hour)
        bp = ax.bxp(stats, positions=np.arange(24) + 0.5, widths=0.6, showfliers=False,
                    patch_artist=True, manage_ticks=False)
        for h in range(24):
            c = COLORS[rate_of(h)]
            bp["boxes"][h].set(facecolor=c, alpha=0.35, edgecolor=c)
            bp["medians"][h].set(color=c, linewidth=2.5)
            for k in (2 * h, 2 * h + 1):
                bp["whiskers"][k].set(color=c)
                bp["caps"][k].set(color=c)

        for a, b, r in segs:
            if r not in peaks:
                continue
            pk = peaks[r]
            ax.hlines(pk, a, b, colors=COLORS[r], linestyles=(0, (5, 3)), linewidth=2, zorder=5)
            if b - a >= 4:
                ax.annotate(
                    f"{L['peak']} {r}: {pk:,.0f} kW", ((a + b) / 2, pk),
                    xytext=(0, 10), textcoords="offset points", ha="center",
                    fontsize=10.5, fontweight="bold", color="#222", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=COLORS[r], lw=1.3),
                )

        ax.set_title(name, loc="left", fontsize=12)
        ax.set_xlim(0, 24)
        ax.set_ylim(0, ymax)
        ax.set_xticks(np.arange(0, 24, 3) + 0.5)
        ax.set_xticklabels(range(0, 24, 3))
        ax.set_ylabel("kW")
        ax.grid(axis="y", alpha=0.25)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)

    for ax, (curve, rate_of, segs, name) in zip(axes, panels):
        panel(ax, curve, rate_of, segs, name)
    axes[-1].set_xlabel(L["hour"])

    fig.suptitle(title, fontsize=14, weight="bold")
    top_margin = 0.965 - (0.045 if bill_total is not None else 0)
    fig.text(
        0.01, 0.005,
        f"Forecast shape only - not a measurement. Median = forecast curve, "
        f"box = ±{BOX_SPREAD_PCT:.0%} / whisker = ±{WHISKER_SPREAD_PCT:.0%} assumed spread (not real variability).",
        fontsize=8, color="gray",
    )
    fig.tight_layout(rect=(0, 0.02, 1, top_margin), h_pad=3.5)
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
    bill_total: Optional[float] = None,
) -> bytes:
    """สร้างกราฟพยากรณ์เส้นโค้ง PNG จากพารามิเตอร์ระดับบิล — ต้องมีอย่างน้อย 1 คู่ peak+energy
    (P, OP หรือ H) raise ValueError ถ้าไม่มีเลยสักคู่ ช่วงที่ไม่ได้กรอก (peak<=0 หรือไม่ส่งมา) จะถูก
    ข้ามไปเฉยๆ ไม่ error — bill_total (ไม่บังคับ) แสดงกำกับบนกราฟเป็นข้อมูลอ้างอิงเฉยๆ ดู draw()"""

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

    fig = draw(curve_wd, curve_h, peaks, bill_total=bill_total)
    return render_png(fig)
