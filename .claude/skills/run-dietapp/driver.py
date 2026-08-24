# DietApp 浏览器驱动(agent 用):python driver.py <scenario>
#
# 前提:后端(8000,指向 dietapp.dev.db 副本)和前端(5173)已在后台启动,
# playwright 已装在 %LOCALAPPDATA%\dietapp-pwlib(或 DIETAPP_PWLIB 指定的目录),
# 用系统 Chrome(channel="chrome")驱动,不需要下载 playwright 自带浏览器。
# 启动/清理命令见同目录 SKILL.md。
#
# 场景(smoke 是默认的代表性交互;其余是 1.9 写入路径的完整人工回归组):
#   smoke            打开记录页 → 发一句闲聊 → 等 AI 回复 → 截图(1 次真实 LLM 调用)
#   happy            发多食物 → 暂存确认+暂存修改 → 两轮顶部确认 → 一条总结气泡
#   clarify_chitchat 追问循环 / 顶部放弃 / 闲聊 / 改已有记录被拒
#   delete_row       今日明细删一行(二次确认)
#   guard            有未确认项时直接打字 → 拦截弹窗 → 放弃并继续
#   resume_setup     制造一个未收尾批次(弹出卡片后直接退出)
#   resume           重新打开 → 恢复弹窗 → 继续重建卡片 → 放弃收尾 → 再刷新不再弹
#
# 截图落在 .claude/skills/run-dietapp/screenshots/(已 gitignore)。
# 全程收集 console error,退出时打印;有 error 不算跑通。

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_PWLIB = os.environ.get("DIETAPP_PWLIB") or str(
    Path(os.environ["LOCALAPPDATA"]) / "dietapp-pwlib"
)
sys.path.insert(0, _PWLIB)

from playwright.sync_api import expect, sync_playwright  # noqa: E402

SHOTS = Path(__file__).parent / "screenshots"
SHOTS.mkdir(exist_ok=True)
APP = "http://127.0.0.1:5173"
LLM_TIMEOUT = 90_000  # 真实 LLM 调用(解析+逐项估算),必须放宽

console_errors: list[str] = []


def shot(page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)
    print(f"[shot] {name}.png")


def send_text(page, text: str, button: str = "发送") -> None:
    page.locator(".input-bar__field").fill(text)
    page.get_by_role("button", name=button).click()


def card(page):
    return page.locator('section[aria-label="解析结果卡片"]')


def top_button(page, label: str):
    return card(page).locator(f'.confirm-card__actions button:has-text("{label}")')


def assistant_bubbles(page) -> int:
    return page.locator(".bubble.assistant").count()


def open_app(page) -> None:
    page.goto(APP)
    expect(page.get_by_role("region", name="今日明细")).to_be_visible(timeout=30_000)
    # 等挂载时的历史消息加载完成再计数(否则气泡基线是 0,断言会错位)
    page.wait_for_timeout(2500)


def expand_today(page) -> None:
    """展开今日明细(点顶部摄入区 = 一键全展开)。

    明细默认全收起、只剩每餐小计,收起时明细行高度为 0——Playwright 命中测试
    落不到删除按钮上(注意 is_visible() 仍是 True,骗人)。凡是要操作明细行,
    先调这个。已经展开时按钮名变成"收起全部明细",这里会跳过。
    """
    toggle = page.get_by_role("button", name="展开全部明细")
    # 今天没有任何记录时这个按钮是 disabled 的,直接 click 会干等 30s 超时
    if toggle.count() > 0 and toggle.is_enabled():
        toggle.click()
        page.wait_for_timeout(400)  # 等展开动画走完


def scenario_smoke(page) -> None:
    """最小代表性交互:页面渲染 + 一次真实对话往返。"""
    open_app(page)
    shot(page, "smoke_01_loaded")
    n0 = assistant_bubbles(page)
    send_text(page, "早上好")
    expect(page.locator(".bubble.assistant")).to_have_count(n0 + 1, timeout=LLM_TIMEOUT)
    shot(page, "smoke_02_replied")
    print("[ok] smoke: app rendered and replied")


def scenario_happy(page) -> None:
    open_app(page)
    n0 = assistant_bubbles(page)
    send_text(page, "中午吃了一碗米饭和两个煮鸡蛋")
    expect(card(page)).to_be_visible(timeout=LLM_TIMEOUT)
    shot(page, "happy_01_card")
    assert assistant_bubbles(page) == n0 + 1, "识别播报应该只有一条"

    rows = card(page).locator(".confirm-item")
    assert rows.count() == 2, f"预期 2 项,实际 {rows.count()}"

    rows.nth(0).locator('button:has-text("确认")').click()
    rows.nth(1).locator('button:has-text("修改")').click()
    expect(page.locator(".input-bar__modify-hint")).to_be_visible()
    send_text(page, "改成三个鸡蛋,大概150克", "确认修改")
    expect(card(page).get_by_text("修改:", exact=False)).to_be_visible()
    shot(page, "happy_02_stashed")

    top_button(page, "确认").click()
    expect(card(page).get_by_text("已写入")).to_be_visible(timeout=LLM_TIMEOUT)
    today = page.get_by_role("region", name="今日明细")
    del_buttons = today.locator('button[aria-label^="删除"]')
    expand_today(page)
    expect(del_buttons.first).to_be_visible(timeout=10_000)
    assert del_buttons.first.is_disabled(), "卡片未结束时删除按钮应禁用"
    expect(card(page).get_by_text("重新估算中…")).to_have_count(0, timeout=LLM_TIMEOUT)
    shot(page, "happy_03_partial_written")

    n_before_final = assistant_bubbles(page)
    remaining = card(page).locator(".confirm-item", has_not=page.get_by_text("已写入"))
    remaining.first.locator('button:has-text("确认")').click()
    top_button(page, "确认").click()
    expect(card(page)).to_have_count(0, timeout=LLM_TIMEOUT)
    expect(page.locator(".bubble.assistant")).to_have_count(
        n_before_final + 1, timeout=LLM_TIMEOUT
    )
    shot(page, "happy_04_recap")
    expand_today(page)
    assert del_buttons.first.is_enabled(), "卡片结束后删除按钮应恢复可用"
    print("[ok] happy path")


def scenario_clarify_chitchat(page) -> None:
    open_app(page)

    n0 = assistant_bubbles(page)
    send_text(page, "我吃了鸡胸肉")
    expect(page.locator(".bubble.assistant")).to_have_count(n0 + 1, timeout=LLM_TIMEOUT)
    assert card(page).count() == 0, "追问期间不应出现卡片"
    shot(page, "clarify_01_question")

    send_text(page, "熟的,大概150克")
    expect(card(page)).to_be_visible(timeout=LLM_TIMEOUT)
    n1 = assistant_bubbles(page)
    top_button(page, "放弃").click()
    expect(card(page)).to_have_count(0, timeout=10_000)
    expect(page.locator(".bubble.assistant")).to_have_count(n1 + 1, timeout=LLM_TIMEOUT)
    shot(page, "clarify_02_abandoned")

    n2 = assistant_bubbles(page)
    send_text(page, "今天天气怎么样?")
    expect(page.locator(".bubble.assistant")).to_have_count(n2 + 1, timeout=LLM_TIMEOUT)
    assert card(page).count() == 0
    shot(page, "clarify_03_chitchat")

    n3 = assistant_bubbles(page)
    send_text(page, "帮我把刚才记的东西删掉")
    expect(page.locator(".bubble.assistant")).to_have_count(n3 + 1, timeout=LLM_TIMEOUT)
    assert card(page).count() == 0
    shot(page, "clarify_04_edit_refused")
    print("[ok] clarify + chitchat + edit_existing")


def scenario_delete_row(page) -> None:
    open_app(page)
    expand_today(page)
    today = page.get_by_role("region", name="今日明细")
    del_buttons = today.locator('button[aria-label^="删除"]')
    before = del_buttons.count()
    assert before >= 1, "需要至少一行可删(先跑 happy)"
    del_buttons.first.click()
    expect(page.get_by_role("alertdialog")).to_be_visible()
    shot(page, "delete_01_dialog")
    page.get_by_role("alertdialog").get_by_role("button", name="删除").click()
    expect(del_buttons).to_have_count(before - 1, timeout=10_000)
    shot(page, "delete_02_done")
    print(f"[ok] delete row: {before} -> {before - 1}")


def scenario_guard(page) -> None:
    open_app(page)
    send_text(page, "晚饭吃了一份100克的清炒西兰花,熟的")
    expect(card(page)).to_be_visible(timeout=LLM_TIMEOUT)

    send_text(page, "早上好")
    expect(page.get_by_role("alertdialog")).to_be_visible()
    shot(page, "guard_01_dialog")
    page.get_by_role("button", name="放弃并继续").click()
    expect(card(page)).to_have_count(0, timeout=10_000)
    expect(page.locator(".bubble.user").last).to_have_text("早上好", timeout=10_000)
    shot(page, "guard_02_continued")
    print("[ok] unconfirmed guard")


def scenario_resume_setup(page) -> None:
    open_app(page)
    send_text(page, "加餐吃了一根香蕉,大概120克")
    expect(card(page)).to_be_visible(timeout=LLM_TIMEOUT)
    shot(page, "resume_00_card_open")
    print("[ok] resume setup: card open, now run scenario `resume`")


def scenario_resume(page) -> None:
    page.goto(APP)
    expect(page.get_by_role("alertdialog")).to_be_visible(timeout=30_000)
    shot(page, "resume_01_dialog")
    page.get_by_role("button", name="继续").click()
    expect(card(page)).to_be_visible(timeout=10_000)
    shot(page, "resume_02_rebuilt")
    n = assistant_bubbles(page)
    top_button(page, "放弃").click()
    expect(card(page)).to_have_count(0, timeout=10_000)
    expect(page.locator(".bubble.assistant")).to_have_count(n + 1, timeout=LLM_TIMEOUT)

    page.goto(APP)
    expect(page.get_by_role("region", name="今日明细")).to_be_visible(timeout=30_000)
    page.wait_for_timeout(2000)
    assert page.get_by_role("alertdialog").count() == 0, "已收尾批次不应再弹恢复提示"
    shot(page, "resume_03_closed")
    print("[ok] resume flow")


SCENARIOS = {
    "smoke": scenario_smoke,
    "happy": scenario_happy,
    "clarify_chitchat": scenario_clarify_chitchat,
    "delete_row": scenario_delete_row,
    "guard": scenario_guard,
    "resume_setup": scenario_resume_setup,
    "resume": scenario_resume,
}


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    if name not in SCENARIOS:
        print(f"未知场景 {name!r},可选: {', '.join(SCENARIOS)}")
        raise SystemExit(2)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on(
            "console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None,
        )
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        try:
            SCENARIOS[name](page)
        except Exception:
            shot(page, f"error_{name}")
            print("[page text dump]")
            print(page.inner_text("body")[:3000])
            raise
        finally:
            if console_errors:
                print("[console errors]")
                for err in console_errors:
                    print(" ", err[:300])
            else:
                print("[console] no errors")
            browser.close()


if __name__ == "__main__":
    main()
