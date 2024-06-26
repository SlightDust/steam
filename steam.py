import json
import os
from lxml import etree
from asyncio import sleep
from datetime import datetime

try:
    from urllib2 import urlopen
except ImportError:
    from urllib.request import urlopen
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from nonebot import MessageSegment

from hoshino import service, aiorequests
from hoshino.util import pic2b64

help_ = """
[添加steam订阅 steamid或自定义url] 订阅一个账号的游戏状态
[取消steam订阅 steamid或自定义url] 取消订阅
[steam订阅列表] 查询本群所有订阅账号的游戏状态
[谁在玩游戏] 看看谁在玩游戏
[查询steam账号] 查询指定steam账号的游戏状态
"""

sv = service.Service("steam", enable_on_default=True, help_=help_)


proxies = None

current_folder = os.path.dirname(__file__)
config_file = os.path.join(current_folder, 'steam.json')
with open(config_file, mode="r") as f:
    f = f.read()
    cfg = json.loads(f)

playing_state = {}


async def format_id(id: str) -> str:
    if id.startswith('76561') and len(id) == 17:
        return id
    else:
        resp = await aiorequests.get(f'https://steamcommunity.com/id/{id}?xml=1', proxies=proxies)
        xml = etree.XML(await resp.content)
        return xml.xpath('/profile/steamID64')[0].text


async def fetch_avatar(url):
    """use aiorequests to fetch avatar"""
    resp = await aiorequests.get(url, proxies=proxies)
    data_stream = BytesIO(await resp.content)
    return Image.open(data_stream)


async def make_img(data):
    top = data["personaname"]
    mid = "is now playing"
    bottom = data["gameextrainfo"]
    url = data["avatarmedium"]

    text_size = 16
    spacing = 20
    font_multilang_path = os.path.join(os.path.dirname(__file__), 'simhei.ttf')
    font_ascii_path = os.path.join(os.path.dirname(__file__), 'tahoma.ttf')
    font_ascii = ImageFont.truetype(font_ascii_path, size=text_size)
    font_multilang = ImageFont.truetype(font_multilang_path, size=text_size)
    avatar = await fetch_avatar(url)
    w = int(280 * 1.6)
    h = 86
    img = Image.new("RGB", (w, h), (33, 33, 33))
    draw = ImageDraw.Draw(img)
    avatar = avatar.resize((60, 60))
    green_line = Image.new("RGB", (3, 60), (89, 191, 64))
    img.paste(avatar, (13, 10))
    img.paste(green_line, (74, 10))
    draw.text((90, 10), top, fill=(193, 217, 167), font=font_multilang)
    draw.text((90, 10 + spacing - 2), mid, fill=(115, 115, 115), font=font_ascii)
    # draw.text((90, 10+spacing*2), bottom, fill=(135, 181, 82), font=font_ascii)

    x_position = 90  # 起始x位置
    for char in bottom:
        current_font = font_ascii
        # 如果当前字体默认字体并且字符不在默认字体中，则切换到回退字体
        if current_font == font_ascii and draw.textlength(char, font=font_ascii) == text_size:
            current_font = font_multilang
        # 绘制字符
        draw.text((x_position, 10 + spacing * 2), text=char, font=current_font, fill=(135, 181, 82))
        # 更新x位置以便下一个字符能紧挨着前一个字符
        x_position += draw.textlength(char, font=current_font)

    # img.show()
    return img


def calculate_last_login_time(last_logoff: int) -> str:
    """
    计算steam距离最后一次登录距离现在时间过去了多次时间, 如果是月份则显示月份，如果是天数则显示天数和小时，如果是小时则显示小时
    :param last_logoff: 最后一次登录时间
    :return: 距离最后一次登录时间过去了多久
    """
    current_time = datetime.now().timestamp()
    time_diff = current_time - last_logoff
    if time_diff > 30 * 24 * 60 * 60:
        return f"{int(time_diff / (30 * 24 * 60 * 60))}月"
    elif time_diff > 24 * 60 * 60:
        return f"{int(time_diff / (24 * 60 * 60))}天{int((time_diff % (24 * 60 * 60)) / 3600)}小时"
    else:
        return f"{int(time_diff / 3600)}小时"


async def generate_subscribe_list_image(group_playing_state: dict) -> Image:
    text_size_normal = 17
    text_size_small = 11
    spacing = 10
    border_size = 10
    green = (144, 186, 60)
    blue = (87, 203, 222)
    gray = (137, 137, 137)
    font_multilang_path = os.path.join(os.path.dirname(__file__), 'simhei.ttf')
    font_ascii_path = os.path.join(os.path.dirname(__file__), 'tahoma.ttf')
    font_ascii = ImageFont.truetype(font_ascii_path, size=text_size_small)
    font_multilang = ImageFont.truetype(font_multilang_path, size=text_size_normal)
    font_multilang_small = ImageFont.truetype(font_multilang_path, size=text_size_small)
    green_line = Image.new("RGB", (3, 48), green)
    blue_line = Image.new("RGB", (3, 48), blue)
    gray_line = Image.new("RGB", (3, 48), gray)
    status_num = len(group_playing_state)
    x = 0
    y = 0
    w = 290
    h = 48 * status_num + spacing * (status_num - 1)
    background = Image.new("RGB", (w, h), (33, 33, 33))
    draw = ImageDraw.Draw(background)
    for steam_id, status in group_playing_state.items():
        player_name = status["personaname"]
        game_info = status["gameextrainfo"]
        avatar_url = status["avatarmedium"]

        is_online = status["personastate"] != 0
        is_playing = game_info != ""

        avatar = await fetch_avatar(avatar_url)
        avatar = avatar.resize((48, 48))
        background.paste(avatar, (x, y))
        padding_top = 8  # 用于调整右侧文字区域的padding top
        padding_left = 5  # 用于调整右侧文字区域的padding left
        if is_playing:
            # 用户名
            draw.text((x + padding_left + 48 + 5, y + padding_top), player_name, fill=green,
                      font=font_multilang)
            background.paste(green_line, (x + 48 + 1, y))
            draw.text((x + padding_left + 48 + 5, y + padding_top + 23), game_info,
                      fill=green,
                      font=font_ascii)
        elif is_online:
            # 用户名
            draw.text((x + padding_left + 48 + 5, y + padding_top), player_name, fill=blue,
                      font=font_multilang)
            # 在线状态的线条
            background.paste(blue_line, (x + 48 + 1, y))
            draw.text((x + padding_left + 48 + 5, y + padding_top + 23), "在线",
                      fill=blue,
                      font=font_multilang_small)
        else:  # offline
            # 用户名
            draw.text((x + padding_left + 48 + 5, y + padding_top), player_name, fill=gray,
                      font=font_multilang)
            # 在线状态的线条
            background.paste(gray_line, (x + 48 + 1, y))
            # 显示离线时间
            if status["lastlogoff"]:  # 是apikey所属账号的好友，可以获取上次在线时间
                last_logoff = f'上次在线{calculate_last_login_time(status["lastlogoff"])}前'
            else:  # 非好友
                last_logoff = "离线"
            draw.text((x + padding_left + 48 + 5, y + padding_top + 23), last_logoff,
                        fill=gray,
                        font=font_multilang_small)
        y += 48 + spacing
    # 给最终结果创建一个环绕四周的边框, 颜色和背景色一致
    result_with_border = Image.new("RGB", (w + border_size * 2, h + border_size * 2), (33, 33, 33))
    result_with_border.paste(background, (border_size, border_size))
    return result_with_border


@sv.on_prefix("添加steam订阅")
async def steam(bot, ev):
    account = str(ev.message).strip()
    try:
        await update_steam_ids(account, ev["group_id"])
        rsp = await get_account_status(account)
        if rsp["personaname"] == "":
            await bot.send(ev, "添加订阅失败！")
        elif rsp["gameextrainfo"] == "":
            await bot.send(ev, f"%s 没在玩游戏！" % rsp["personaname"])
        else:
            await bot.send(ev, f"%s 正在玩 %s ！" % (rsp["personaname"], rsp["gameextrainfo"]))
        await bot.send(ev, "订阅成功")
    except:
        await bot.send(ev, "订阅失败")


@sv.on_prefix("取消steam订阅")
async def steam(bot, ev):
    account = str(ev.message).strip()
    try:
        await del_steam_ids(account, ev["group_id"])
        await bot.send(ev, "取消订阅成功")
    except:
        await bot.send(ev, "取消订阅失败")


@sv.on_fullmatch(("steam订阅列表", "谁在玩游戏"))
async def steam(bot, ev):
    group_id = ev["group_id"]
    group_state_dict = {}
    await update_game_status()
    for key, val in playing_state.items():
        if group_id in cfg["subscribes"][str(key)]:
            group_state_dict[key] = val
    if len(group_state_dict) == 0:
        await bot.send(ev, "没有订阅的steam账号！")
        return
    img = await generate_subscribe_list_image(group_state_dict)
    msg = MessageSegment.image(pic2b64(img))
    await bot.send(ev, msg)


@sv.on_prefix("查询steam账号")
async def steam(bot, ev):
    account = str(ev.message).strip()
    rsp = await get_account_status(account)
    if rsp["personaname"] == "":
        await bot.send(ev, "查询失败！")
    elif rsp["gameextrainfo"] == "":
        await bot.send(ev, f"%s 没在玩游戏！" % rsp["personaname"])
    else:
        await bot.send(ev, f"%s 正在玩 %s ！" % (rsp["personaname"], rsp["gameextrainfo"]))


async def get_account_status(id) -> dict:
    id = await format_id(id)
    params = {
        "key": cfg["key"],
        "format": "json",
        "steamids": id
    }
    resp = await aiorequests.get("https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/", params=params,
                                 proxies=proxies)
    rsp = await resp.json()
    friend = rsp["response"]["players"][0]
    return {
        "personaname": friend["personaname"] if "personaname" in friend else "",
        "gameextrainfo": friend["gameextrainfo"] if "gameextrainfo" in friend else ""
    }


async def update_game_status():
    params = {
        "key": cfg["key"],
        "format": "json",
        "steamids": ",".join(cfg["subscribes"].keys())
    }
    resp = await aiorequests.get("https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/", params=params,
                                 proxies=proxies)
    rsp = await resp.json()
    for player in rsp["response"]["players"]:
        playing_state[player["steamid"]] = {
            "personaname": player["personaname"],
            # "lastlogoff": player["lastlogoff"],
            # steam personastate detail:  0 - Offline, 1 - Online, 2 - Busy, 3 - Away,
            #  4 - Snooze, 5 - looking to trade, 6 - looking to play.
            "personastate": player["personastate"],
            "gameextrainfo": player["gameextrainfo"] if "gameextrainfo" in player else "",
            "avatarmedium": player["avatarmedium"],
        }
        # 非steam好友，没有lastlogoff字段，置为None供generate_subscribe_list_image判断
        if "lastlogoff" in player:
            playing_state[player["steamid"]]["lastlogoff"] = player["lastlogoff"]
        else:
            playing_state[player["steamid"]]["lastlogoff"] = None


async def update_steam_ids(steam_id, group):
    steam_id = await format_id(steam_id)
    if steam_id not in cfg["subscribes"]:
        cfg["subscribes"][str(steam_id)] = []
    if group not in cfg["subscribes"][str(steam_id)]:
        cfg["subscribes"][str(steam_id)].append(group)
    with open(config_file, mode="w") as fil:
        json.dump(cfg, fil, indent=4, ensure_ascii=False)
    await update_game_status()


async def del_steam_ids(steam_id, group):
    steam_id = await format_id(steam_id)
    if group in cfg["subscribes"][str(steam_id)]:
        cfg["subscribes"][str(steam_id)].remove(group)
    with open(config_file, mode="w") as fil:
        json.dump(cfg, fil, indent=4, ensure_ascii=False)
    await update_game_status()


@sv.scheduled_job('cron', minute='*/2')
async def check_steam_status():
    old_state = playing_state.copy()
    await update_game_status()
    for key, val in playing_state.items():
        try:
            if val["gameextrainfo"] != old_state[key]["gameextrainfo"]:
                glist = set(cfg["subscribes"][key]) & set((await sv.get_enable_groups()).keys())
                if val["gameextrainfo"] == "":
                    await broadcast(glist,
                                    "%s 不玩 %s 了！" % (val["personaname"], old_state[key]["gameextrainfo"]))
                else:
                    # await broadcast(glist,
                    #                 "%s 正在游玩 %s ！" % (val["personaname"], val["gameextrainfo"]))
                    await broadcast(glist, MessageSegment.image(pic2b64(await make_img(playing_state[key]))))
        except Exception as e:
            sv.logger.warning(f"check_steam_status error: {e}, key: {key}, val: {val}, skipped.")


async def broadcast(group_list: set, msg):
    for group in group_list:
        await sv.bot.send_group_msg(group_id=group, message=msg)
        await sleep(0.5)
