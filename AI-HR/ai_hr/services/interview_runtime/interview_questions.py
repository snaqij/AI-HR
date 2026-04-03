"""面试固定话术与非技术题库。"""

import random

# P1: 开场引导模板 (直接引导自我介绍)
P1_TEMPLATES = [
    "你好，我是今天的面试官。我已经看过了你的简历，感觉背景非常契合。为了互相了解，请先做一个简短的自我介绍吧。",
    "你好，很高兴能和你交流。我看过你的简历，非常有竞争力。我们直接进入正题，请先结合简历介绍一下你自己。",
    "你好，我是面试官。我已经详细了解过你的经历，下面请先简单介绍一下你的背景和核心项目经历。",
    "你好！我看过你的简历，对你在项目中的表现很感兴趣。首先请你先花几分钟做个自我介绍吧。"
]

# P5: 非技术类综合素质题库
P5_QUESTIONS = [
    {
        "question": "如果你通过了面试，最快什么时候能到岗？",
        "dimension": "availability",
        "expected_signal": "明确日期、入职意向"
    },
    {
        "question": "你期望的实习时间是多久？每周能保证几天在岗？",
        "dimension": "internship_duration",
        "expected_signal": "时间跨度、出勤率"
    },
    {
        "question": "你对自己未来 3-5 年的职业规划是怎样的？",
        "dimension": "career_planning",
        "expected_signal": "目标明确、学习意愿、稳定性"
    },
    {
        "question": "请分享一次你在压力下或面临截止日期时完成任务的经历。",
        "dimension": "resilience",
        "expected_signal": "抗压能力、任务拆解、情绪调节"
    },
    {
        "question": "如果在项目中与同事或上司产生技术分歧，你会如何处理？",
        "dimension": "communication",
        "expected_signal": "客观评估、沟通技巧、团队利益"
    }
]

# P6: 企业介绍与收尾模板
P6_TEMPLATES = [
    (
        "在面试结束前，我简单介绍一下我们公司。我们专注于 AI 与人力资源领域的结合，致力于用顶级技术提升招聘效率，目前正处于高速发展期。\n"
        "今天的面试就到这里，非常感谢你的参与和分享，请耐心等待后续通知。再见。"
    ),
    (
        "关于我们公司，我们是行业领先的技术驱动型商业平台，目前在 AI 赋能方面有很大投入，团队氛围也非常务实和敏捷。\n"
        "感谢你今天的表现，面试到此结束，具体结果我们会通过系统或招聘软件告知你。祝你有愉快的一天。"
    ),
    (
        "我们公司目前正致力于打造业内最先进的 AI 招聘引擎，技术挑战很大，也很有成就感。面试过程很愉快，你的背景我们也留下了深刻印象。\n"
        "今天的交流就到这里，后续 HR 会和你联系。感谢参加，再见。"
    )
]

def get_random_p1():
    """随机获取一个开场引导"""
    return random.choice(P1_TEMPLATES)

def get_random_p5(count=2):
    """随机获取 N 个非技术问题"""
    return random.sample(P5_QUESTIONS, min(count, len(P5_QUESTIONS)))

def get_random_p6():
    """随机获取一个收尾介绍"""
    return random.choice(P6_TEMPLATES)
