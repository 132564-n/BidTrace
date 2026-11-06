"""Build two fictional bid PDFs for the documented evaluation set."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "fixtures" / "bids"
OUTPUT.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont("SimHei", r"C:\Windows\Fonts\simhei.ttf"))

TITLE = ParagraphStyle(
    "title", fontName="SimHei", fontSize=22, leading=32, alignment=TA_CENTER,
    textColor=colors.HexColor("#17324d"), spaceAfter=15 * mm, wordWrap="CJK"
)
HEADING = ParagraphStyle(
    "heading", fontName="SimHei", fontSize=16, leading=24, alignment=TA_LEFT,
    textColor=colors.HexColor("#17324d"), spaceAfter=9 * mm, wordWrap="CJK"
)
BODY = ParagraphStyle(
    "body", fontName="SimHei", fontSize=11, leading=19, alignment=TA_LEFT,
    textColor=colors.HexColor("#243746"), spaceAfter=5 * mm, wordWrap="CJK"
)
NOTE = ParagraphStyle(
    "note", fontName="SimHei", fontSize=10, leading=17, alignment=TA_LEFT,
    textColor=colors.HexColor("#596a78"), spaceAfter=5 * mm, wordWrap="CJK"
)


def para(value: str, style=BODY):
    return Paragraph(escape(value), style)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d7dfe5"))
    canvas.line(23 * mm, 20 * mm, 187 * mm, 20 * mm)
    canvas.setFont("SimHei", 8)
    canvas.setFillColor(colors.HexColor("#6c7985"))
    canvas.drawString(23 * mm, 14 * mm, "模拟投标文件 · 仅供审核系统测试")
    canvas.drawRightString(187 * mm, 14 * mm, f"PDF 第 {doc.page} 页")
    canvas.restoreState()


COMMON = [
    (
        "封面与使用说明",
        [
            "项目名称：2025 年信息化城市管理运行",
            "项目编号：11000025210200116100-XM001",
            "投标人：示例供应商（虚构）",
            "本文件完全为软件测试而编写，不含真实企业资质、签章或投标承诺，不得用于实际投标。",
            "两份样本分别用于检验审核系统对明确冲突、未找到证据和需人工复核的识别能力。",
        ],
    ),
    (
        "投标书",
        [
            "致：北京市城市运行管理事务中心。示例供应商参加本项目投标，并响应招标文件的采购需求。",
            "我方提交的投标材料仅作为模拟审核样本。",
        ],
    ),
    (
        "报价及商务响应",
        [
            "本节列出投标总报价和项目实施期限，其他结算条件以招标文件为准。",
        ],
    ),
    (
        "项目团队和现场保障",
        [
            "项目团队负责日常监测、现场沟通、报告复核和突发事件响应。",
        ],
    ),
    (
        "网格化城市管理运行方案",
        [
            "通过问题受理流程对不同来源的城市管理问题进行登记、核实、任务分转、催办、结果反馈、委托核查和办结。",
            "对于疑难问题，协助协调、分派和跟踪处置流程，对超时问题开展催办。",
        ],
    ),
    (
        "网格问题质量控制",
        [
            "本节描述网格问题数据的质量分析和日常统计安排。",
        ],
    ),
    (
        "首都环境建设考评运行方案",
        [
            "建立环境问题台账，核对问题类别、图片和位置信息，按属地和权属分派任务，并留存处置记录。",
            "依托视频监控点位开展巡查，发现问题后登记录入并纳入办理流程。",
        ],
    ),
    (
        "城市运行监测方案",
        [
            "对城市运行监测系统中的数据进行收集、汇总和异常分析。",
        ],
    ),
    (
        "项目实施方案",
        [
            "实施分为启动、规则梳理、日常运行、质量复盘和验收五个阶段。",
            "网格化城市管理、城市运行监测与首都环境建设考评三个工作域分别设置负责人和质量复核人。",
        ],
    ),
]


def sections(flawed: bool):
    pages = [(title, list(lines)) for title, lines in COMMON]
    pages[1][1].append(
        "本投标有效期为自提交投标文件截止之日起60日历天。" if flawed
        else "本投标有效期为自提交投标文件截止之日起90日历天。"
    )
    pages[2][1].extend(
        ["投标总报价为150万元。", "项目实施期限为自合同签订之日起18个月。"]
        if flawed else
        ["投标总报价为140万元。", "项目实施期限为自合同签订之日起12个月。"]
    )
    pages[3][1].extend(
        ["本项目不设专职项目负责人。", "现场值守时间为每周5天、每日8小时。"]
        if flawed else
        ["本项目设置项目负责人1名，统一管理并复核报送材料。", "团队可提供每周7天、每天24小时现场值守。"]
    )
    pages[5][1].append(
        "拟建立问题质量分析机制，开展抽查并形成相关日常记录。" if flawed
        else "利用网格问题密度识别高频区域，生成定向抽查清单，开展问题质量抽查；对不符合标准的问题单作标记，并形成日报。"
    )
    pages[7][1].append(
        "监测安排为每周一至周五收集数据，并在工作日编制《综合信息》。" if flawed
        else "每日（包含节假日）监测并收集不同渠道的城市运行数据，发现异常及时处理；每日（包含节假日）汇总并编制《综合信息》。"
    )
    if not flawed:
        pages.append((
            "培训方案",
            [
                "培训对象包括项目负责人、网格问题处理人员和城市运行监测人员。",
                "培训内容包括问题派发规则、异常数据处理、报告编制和应急值守流程。",
                "时间计划为项目启动后第1周完成基础培训，第2周完成现场演练，此后每季度复训一次。",
            ],
        ))
    pages.append((
        "项目保障方案",
        [
            "质量控制措施：每日检查数据完整性和问题流转记录，每周复核异常处置台账。",
            "故障响应服务方案：接到故障通知后登记、分级、派单并跟踪恢复。",
            "重点时期保障服务方案：重大活动和极端天气期间增派值守人员，调整监测与报告频次。",
        ],
    ))
    return pages


def build(path: Path, flawed: bool):
    story = []
    for index, (title, lines) in enumerate(sections(flawed)):
        if index in {1, 3, 5, 7, 9}:
            story.append(PageBreak())
        if index == 0:
            story.extend([Spacer(1, 25 * mm), para("模拟投标文件", TITLE), Spacer(1, 8 * mm)])
        story.append(para(title, HEADING))
        for line in lines:
            story.append(para(line, NOTE if index == 0 else BODY))
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=23 * mm, rightMargin=23 * mm,
        topMargin=24 * mm, bottomMargin=28 * mm,
        title="模拟投标文件（仅供审核系统测试）",
        author="Bid Review Agent Demo",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    build(OUTPUT / "模拟投标文件-符合样本.pdf", flawed=False)
    build(OUTPUT / "模拟投标文件-问题样本.pdf", flawed=True)
    print("已生成两份模拟投标文件。")
