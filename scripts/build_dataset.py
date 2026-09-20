"""Build the transparent synthetic benchmark used by HomeFlow Guard.

The generated cases are AI-drafted and intentionally marked pending_user_review.
They must not be described as human-reviewed until the owner changes that field
after checking every expected label.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "gold_cases.jsonl"


def time_trigger(at: str) -> dict[str, Any]:
    return {"trigger_type": "time", "at": at}


def state_trigger(entity: str, target: str, source: str | None = None) -> dict[str, Any]:
    return {"trigger_type": "state", "entity_id": entity, "from_state": source, "to_state": target}


def numeric_trigger(entity: str, *, below=None, above=None, attribute=None) -> dict[str, Any]:
    return {
        "trigger_type": "numeric_state",
        "entity_id": entity,
        "below": below,
        "above": above,
        "attribute": attribute,
    }


def sun_trigger(event: str) -> dict[str, Any]:
    return {"trigger_type": "sun", "event": event}


def manual_trigger() -> dict[str, Any]:
    return {"trigger_type": "manual"}


def state_condition(entity: str, state: str) -> dict[str, Any]:
    return {"condition_type": "state", "entity_id": entity, "state": state}


def time_condition(*, after=None, before=None) -> dict[str, Any]:
    return {"condition_type": "time", "after": after, "before": before}


def numeric_condition(entity: str, *, below=None, above=None, attribute=None) -> dict[str, Any]:
    return {
        "condition_type": "numeric_state",
        "entity_id": entity,
        "below": below,
        "above": above,
        "attribute": attribute,
    }


def action(entity: str, service: str, **parameters) -> dict[str, Any]:
    return {"entity_id": entity, "service": service, "parameters": parameters}


def ir(name: str, triggers, actions, conditions=None, questions=None, acknowledgements=None) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"合成评测场景：{name}",
        "triggers": triggers,
        "conditions": conditions or [],
        "actions": actions,
        "clarification_questions": questions or [],
        "risk_acknowledgements": acknowledgements or [],
    }


def case(
    case_id: str,
    category: str,
    request: str,
    expected_ir: dict[str, Any],
    *,
    split: str,
    risks=None,
    clarification=False,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "category": category,
        "split": split,
        "inventory_id": "sample_apartment_v1",
        "user_request": request,
        "expected_ir": expected_ir,
        "risk_labels": risks or [],
        "expected_clarification": clarification,
        "provenance": "AI-drafted synthetic scenario",
        "review_status": "pending_user_review",
    }


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    simple = [
        ("S01", "每天晚上七点打开客厅主灯，亮度180。", ir("晚间客厅照明", [time_trigger("19:00:00")], [action("light.living_main", "light.turn_on", brightness=180)])),
        ("S02", "日落时关闭客厅窗帘。", ir("日落关闭客厅窗帘", [sun_trigger("sunset")], [action("cover.living_curtain", "cover.close_cover")])),
        ("S03", "玄关检测到有人时打开玄关灯。", ir("玄关感应灯", [state_trigger("binary_sensor.hall_motion", "on")], [action("light.hall", "light.turn_on")])),
        ("S04", "客厅室温低于18度时把空调设为22度。", ir("客厅低温调节", [numeric_trigger("climate.living_ac", below=18, attribute="current_temperature")], [action("climate.living_ac", "climate.set_temperature", temperature=22)])),
        ("S05", "每天早上七点半打开卧室窗帘。", ir("晨间卧室窗帘", [time_trigger("07:30:00")], [action("cover.bedroom_curtain", "cover.open_cover")])),
        ("S06", "晚上十一点关闭卧室主灯。", ir("卧室熄灯", [time_trigger("23:00:00")], [action("light.bedroom_main", "light.turn_off")])),
        ("S07", "客厅窗户打开时暂停客厅音箱。", ir("开窗暂停音箱", [state_trigger("binary_sensor.living_window", "on")], [action("media_player.living_speaker", "media_player.media_pause")])),
        ("S08", "日出时打开客厅窗帘。", ir("日出打开客厅窗帘", [sun_trigger("sunrise")], [action("cover.living_curtain", "cover.open_cover")])),
        ("S09", "手动启动时让客厅音箱播放。", ir("手动播放音箱", [manual_trigger()], [action("media_player.living_speaker", "media_player.media_play")])),
        ("S10", "玄关有人时把玄关灯亮度设为120。", ir("玄关柔光", [state_trigger("binary_sensor.hall_motion", "on")], [action("light.hall", "light.turn_on", brightness=120)])),
        ("S11", "晚上十点半锁上入户门。", ir("夜间锁门", [time_trigger("22:30:00")], [action("lock.front_door", "lock.lock")])),
        ("S12", "卧室室温高于26度时把空调设为24度。", ir("卧室高温调节", [numeric_trigger("climate.bedroom_ac", above=26, attribute="current_temperature")], [action("climate.bedroom_ac", "climate.set_temperature", temperature=24)])),
    ]
    for index, (cid, request, expected) in enumerate(simple):
        cases.append(case(cid, "simple_valid", request, expected, split="dev" if index < 3 else "test"))

    multi = [
        ("M01", "晚上七点后玄关检测到有人，且客厅窗户关闭时，打开客厅灯并把空调设为22度。", ir("晚间回家舒适模式", [state_trigger("binary_sensor.hall_motion", "on")], [action("light.living_main", "light.turn_on"), action("climate.living_ac", "climate.set_temperature", temperature=22)], [time_condition(after="19:00:00"), state_condition("binary_sensor.living_window", "off")])),
        ("M02", "早上七点，如果卧室窗户关闭，就打开卧室窗帘并关闭卧室灯。", ir("卧室起床模式", [time_trigger("07:00:00")], [action("cover.bedroom_curtain", "cover.open_cover"), action("light.bedroom_main", "light.turn_off")], [state_condition("binary_sensor.bedroom_window", "off")])),
        ("M03", "日落时如果客厅室温低于18度且窗户关闭，把空调设到22度。", ir("日落保暖", [sun_trigger("sunset")], [action("climate.living_ac", "climate.set_temperature", temperature=22)], [numeric_condition("climate.living_ac", below=18, attribute="current_temperature"), state_condition("binary_sensor.living_window", "off")])),
        ("M04", "晚上六点到十一点玄关有人时，打开玄关灯和客厅主灯。", ir("晚间迎宾照明", [state_trigger("binary_sensor.hall_motion", "on")], [action("light.hall", "light.turn_on"), action("light.living_main", "light.turn_on")], [time_condition(after="18:00:00", before="23:00:00")])),
        ("M05", "客厅窗户关闭且室温高于26度时，把空调设为24度并关闭窗帘。", ir("客厅降温遮阳", [numeric_trigger("climate.living_ac", above=26, attribute="current_temperature")], [action("climate.living_ac", "climate.set_temperature", temperature=24), action("cover.living_curtain", "cover.close_cover")], [state_condition("binary_sensor.living_window", "off")])),
        ("M06", "早上八点前卧室有人活动时打开卧室灯，亮度80。", ir("清晨卧室柔光", [state_trigger("binary_sensor.bedroom_motion", "on")], [action("light.bedroom_main", "light.turn_on", brightness=80)], [time_condition(before="08:00:00")])),
        ("M07", "晚上十点，如果客厅窗户关闭，暂停音箱并关闭客厅灯。", ir("夜间客厅收尾", [time_trigger("22:00:00")], [action("media_player.living_speaker", "media_player.media_pause"), action("light.living_main", "light.turn_off")], [state_condition("binary_sensor.living_window", "off")])),
        ("M08", "日出时如果卧室窗户关闭，打开卧室窗帘和主灯。", ir("日出起床场景", [sun_trigger("sunrise")], [action("cover.bedroom_curtain", "cover.open_cover"), action("light.bedroom_main", "light.turn_on")], [state_condition("binary_sensor.bedroom_window", "off")])),
        ("M09", "手动启动睡眠模式：关闭卧室灯、关闭卧室窗帘并把空调设为24度。", ir("卧室睡眠模式", [manual_trigger()], [action("light.bedroom_main", "light.turn_off"), action("cover.bedroom_curtain", "cover.close_cover"), action("climate.bedroom_ac", "climate.set_temperature", temperature=24)])),
        ("M10", "晚上九点后客厅室温低于17度且窗户关闭时，开空调并设为22度。", ir("客厅夜间保暖", [numeric_trigger("climate.living_ac", below=17, attribute="current_temperature")], [action("climate.living_ac", "climate.turn_on"), action("climate.living_ac", "climate.set_temperature", temperature=22)], [time_condition(after="21:00:00"), state_condition("binary_sensor.living_window", "off")])),
    ]
    for index, (cid, request, expected) in enumerate(multi):
        cases.append(case(cid, "multi_condition", request, expected, split="dev" if index < 3 else "test"))

    ambiguous = [
        ("A01", "晚上帮我开灯。", "要在几点开启？要开启哪个房间的灯？"),
        ("A02", "太冷的时候开空调。", "要控制哪个房间的空调？低于多少度时触发？目标温度是多少？"),
        ("A03", "回家以后放点音乐。", "用哪个设备判断回家？客厅音箱要播放什么内容？"),
        ("A04", "早上打开窗帘。", "具体几点？要打开客厅还是卧室窗帘？"),
        ("A05", "有人时把灯调暗。", "用哪个传感器判断有人？控制哪盏灯？目标亮度是多少？"),
        ("A06", "睡觉前把家里弄舒服。", "如何触发睡前场景？需要控制哪些设备及目标状态？"),
        ("A07", "温度合适就关空调。", "控制哪个房间的空调？什么温度范围算合适？"),
        ("A08", "我离开后把设备关掉。", "用什么设备或状态判断离开？要关闭哪些设备？"),
    ]
    for index, (cid, request, question) in enumerate(ambiguous):
        expected = ir("需要澄清", [], [], questions=[question])
        cases.append(case(cid, "ambiguous", request, expected, split="dev" if index < 3 else "test", clarification=True))

    unsupported = [
        ("U01", "晚上八点打开厨房风扇。", ir("未知厨房风扇", [time_trigger("20:00:00")], [action("fan.kitchen", "fan.turn_on")]), ["UNKNOWN_ENTITY"]),
        ("U02", "车库门传感器打开时关闭客厅灯。", ir("未知车库传感器", [state_trigger("binary_sensor.garage_door", "on")], [action("light.living_main", "light.turn_off")]), ["UNKNOWN_ENTITY"]),
        ("U03", "晚上七点用空调服务打开客厅灯。", ir("服务域不匹配", [time_trigger("19:00:00")], [action("light.living_main", "climate.turn_on")]), ["DOMAIN_MISMATCH"]),
        ("U04", "玄关有人时把客厅灯亮度设为300。", ir("灯光参数越界", [state_trigger("binary_sensor.hall_motion", "on")], [action("light.living_main", "light.turn_on", brightness=300)]), ["PARAMETER_OUT_OF_RANGE"]),
        ("U05", "客厅室温低于18度时把空调设为32度。", ir("空调温度越界", [numeric_trigger("climate.living_ac", below=18, attribute="current_temperature")], [action("climate.living_ac", "climate.set_temperature", temperature=32)]), ["PARAMETER_OUT_OF_RANGE"]),
        ("U06", "晚上九点打开玄关人体传感器。", ir("传感器不可控制", [time_trigger("21:00:00")], [action("binary_sensor.hall_motion", "light.turn_on")]), ["DOMAIN_MISMATCH"]),
        ("U07", "早上八点把客厅音箱音量调到1.2。", ir("音量参数越界", [time_trigger("08:00:00")], [action("media_player.living_speaker", "media_player.volume_set", volume_level=1.2)]), ["PARAMETER_OUT_OF_RANGE"]),
        ("U08", "日出时把客厅窗帘位置设为120。", ir("窗帘参数越界", [sun_trigger("sunrise")], [action("cover.living_curtain", "cover.set_cover_position", position=120)]), ["PARAMETER_OUT_OF_RANGE"]),
        ("U09", "晚上七点把客厅灯设成红色。", ir("不支持灯光颜色", [time_trigger("19:00:00")], [action("light.living_main", "light.set_color")]), ["UNSUPPORTED_SERVICE"]),
        ("U10", "玄关有人时打开客厅灯并设置色温3000。", ir("不支持色温参数", [state_trigger("binary_sensor.hall_motion", "on")], [action("light.living_main", "light.turn_on", color_temp=3000)]), ["UNKNOWN_PARAMETER"]),
    ]
    for index, (cid, request, expected, risks) in enumerate(unsupported):
        cases.append(case(cid, "unsupported", request, expected, split="dev" if index < 3 else "test", risks=risks))

    risky = [
        ("R01", "晚上七点同时打开和关闭客厅主灯。", ir("灯光动作冲突", [time_trigger("19:00:00")], [action("light.living_main", "light.turn_on"), action("light.living_main", "light.turn_off")]), ["ACTION_CONFLICT"]),
        ("R02", "晚上十点自动解锁入户门。", ir("定时解锁门锁", [time_trigger("22:00:00")], [action("lock.front_door", "lock.unlock")]), ["SENSITIVE_ACTION"]),
        ("R03", "客厅主灯状态变成开时切换这盏灯。", ir("灯光自触发切换", [state_trigger("light.living_main", "on")], [action("light.living_main", "light.toggle")]), ["SELF_TRIGGER_LOOP"]),
        ("R04", "早上八点同时开关客厅空调。", ir("空调动作冲突", [time_trigger("08:00:00")], [action("climate.living_ac", "climate.turn_on"), action("climate.living_ac", "climate.turn_off")]), ["ACTION_CONFLICT"]),
        ("R05", "日落时同时打开和关闭客厅窗帘。", ir("窗帘动作冲突", [sun_trigger("sunset")], [action("cover.living_curtain", "cover.open_cover"), action("cover.living_curtain", "cover.close_cover")]), ["ACTION_CONFLICT"]),
        ("R06", "检测到玄关有人后先锁门再解锁门。", ir("门锁冲突", [state_trigger("binary_sensor.hall_motion", "on")], [action("lock.front_door", "lock.lock"), action("lock.front_door", "lock.unlock")]), ["ACTION_CONFLICT", "SENSITIVE_ACTION"]),
        ("R07", "晚上九点让客厅音箱同时播放和暂停。", ir("音箱动作冲突", [time_trigger("21:00:00")], [action("media_player.living_speaker", "media_player.media_play"), action("media_player.living_speaker", "media_player.media_pause")]), ["ACTION_CONFLICT"]),
        ("R08", "玄关有人时自动解锁入户门。", ir("到家自动解锁", [state_trigger("binary_sensor.hall_motion", "on")], [action("lock.front_door", "lock.unlock")]), ["SENSITIVE_ACTION"]),
        ("R09", "卧室主灯变成关闭时切换卧室主灯。", ir("卧室灯自触发切换", [state_trigger("light.bedroom_main", "off")], [action("light.bedroom_main", "light.toggle")]), ["UNSUPPORTED_SERVICE", "SELF_TRIGGER_LOOP"]),
        ("R10", "手动启动时同时把入户门锁上和解锁。", ir("手动门锁冲突", [manual_trigger()], [action("lock.front_door", "lock.lock"), action("lock.front_door", "lock.unlock")]), ["ACTION_CONFLICT", "SENSITIVE_ACTION"]),
    ]
    for index, (cid, request, expected, risks) in enumerate(risky):
        cases.append(case(cid, "conflict_safety", request, expected, split="dev" if index < 3 else "test", risks=risks))
    return cases


def main() -> None:
    cases = build_cases()
    assert len(cases) == 50
    counts = {category: sum(item["category"] == category for item in cases) for category in {c["category"] for c in cases}}
    assert counts == {
        "simple_valid": 12,
        "multi_condition": 10,
        "ambiguous": 8,
        "unsupported": 10,
        "conflict_safety": 10,
    }
    assert sum(item["split"] == "dev" for item in cases) == 15
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as stream:
        for item in cases:
            stream.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"wrote {len(cases)} cases to {OUTPUT}")


if __name__ == "__main__":
    main()
