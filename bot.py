import os
import json
import re
import xml.etree.ElementTree as ET

import requests
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv


# ============================================================
# CONFIGURAÇÃO
# ============================================================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

SHOP_CHANNEL_ID = int(
    os.getenv("DISCORD_SHOP_CHANNEL_ID", "0")
)

NEWS_CHANNEL_ID = int(
    os.getenv("DISCORD_NEWS_CHANNEL_ID", "0")
)

POLL_SECONDS = int(
    os.getenv("POLL_SECONDS", "60")
)

RSS_URL = "https://fxtwitter.com/HYPEX/feed.xml"

STATE_FILE = "state.json"


# ============================================================
# ESTADO
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {
            "posted_ids": []
        }

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if not isinstance(data, dict):

            return {
                "posted_ids": []
            }

        if "posted_ids" not in data:

            data["posted_ids"] = []

        return data

    except Exception as error:

        print(
            f"⚠️ Erro ao carregar state.json: "
            f"{error}"
        )

        return {
            "posted_ids": []
        }


def save_state(state):

    try:

        with open(
            STATE_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                state,
                file,
                indent=2,
                ensure_ascii=False
            )

    except Exception as error:

        print(
            f"❌ Erro ao guardar state.json: "
            f"{error}"
        )


state = load_state()


# ============================================================
# DISCORD
# ============================================================

intents = discord.Intents.default()

intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# ITEM SHOP
# ============================================================

def is_shop_post(title):

    text = title.lower()

    keywords = [

        "item shop",
        "itemshop",
        "fortnite shop",
        "shop tonight",
        "shop today",
        "in the shop",
        "are in the shop",
        "is in the shop",
        "returns tonight",
        "return tonight",
        "available now",
        "out now",
        "bundle out now",
        "bundle tonight",
        "emote is out",
        "emote is back",
        "skins are in the shop",
        "skins return",
        "return to the shop",
        "returning to the shop",
        "leaked fortnite shop",

    ]

    return any(
        keyword in text
        for keyword in keywords
    )


# ============================================================
# EXTRAIR MEDIA DO RSS
# ============================================================

def extract_media(item):

    media = []

    for element in item.iter():

        if not isinstance(
            element.tag,
            str
        ):
            continue

        tag = element.tag.split(
            "}"
        )[-1].lower()

        # ====================================================
        # ENCLOSURE
        # ====================================================

        if tag == "enclosure":

            url = element.attrib.get(
                "url",
                ""
            )

            media_type = element.attrib.get(
                "type",
                ""
            ).lower()

            if not url:
                continue

            if (
                "video" in media_type
                or url.lower().endswith(".mp4")
            ):

                media_type = "video"

            elif (
                "image" in media_type
                or any(
                    extension in url.lower()
                    for extension in [
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                        ".gif"
                    ]
                )
            ):

                media_type = "image"

            else:

                media_type = "image"

            media.append({
                "url": url,
                "type": media_type
            })

        # ====================================================
        # MEDIA CONTENT
        # ====================================================

        elif tag == "content":

            url = element.attrib.get(
                "url",
                ""
            )

            media_type = element.attrib.get(
                "type",
                ""
            ).lower()

            if not url:
                continue

            if "video" in media_type:

                media.append({
                    "url": url,
                    "type": "video"
                })

            elif "image" in media_type:

                media.append({
                    "url": url,
                    "type": "image"
                })

        # ====================================================
        # THUMBNAIL
        # ====================================================

        elif tag == "thumbnail":

            url = element.attrib.get(
                "url",
                ""
            )

            if url:

                media.append({
                    "url": url,
                    "type": "image"
                })

    # ========================================================
    # REMOVER DUPLICADOS
    # ========================================================

    unique_media = []

    seen_urls = set()

    for media_item in media:

        url = media_item["url"]

        if url in seen_urls:
            continue

        seen_urls.add(url)

        unique_media.append(
            media_item
        )

    return unique_media


# ============================================================
# OBTER POSTS DO HYPEX
# ============================================================

def get_latest_posts():

    headers = {

        "User-Agent": "Mozilla/5.0",

        "Accept": (
            "application/rss+xml, "
            "application/xml, "
            "text/xml, "
            "*/*"
        ),

    }

    try:

        response = requests.get(
            RSS_URL,
            headers=headers,
            timeout=20
        )

        print(
            f"📡 FxTwitter RSS HTTP: "
            f"{response.status_code}"
        )

        if response.status_code != 200:

            print(
                f"❌ FxTwitter respondeu HTTP "
                f"{response.status_code}"
            )

            return []

        xml_data = response.text

    except requests.RequestException as error:

        print(
            f"❌ Erro ao contactar FxTwitter: "
            f"{error}"
        )

        return []

    except Exception as error:

        print(
            f"❌ Erro inesperado: "
            f"{error}"
        )

        return []

    # ========================================================
    # LER XML
    # ========================================================

    try:

        root = ET.fromstring(
            xml_data
        )

    except ET.ParseError as error:

        print(
            f"❌ RSS inválido: "
            f"{error}"
        )

        return []

    channel = root.find(
        "channel"
    )

    if channel is None:

        print(
            "❌ RSS não contém channel."
        )

        return []

    posts = []

    # ========================================================
    # LER POSTS
    # ========================================================

    for item in channel.findall(
        "item"
    ):

        title_element = item.find(
            "title"
        )

        link_element = item.find(
            "link"
        )

        guid_element = item.find(
            "guid"
        )

        date_element = item.find(
            "pubDate"
        )

        title = (

            title_element.text.strip()

            if (
                title_element is not None
                and title_element.text
            )

            else ""

        )

        link = (

            link_element.text.strip()

            if (
                link_element is not None
                and link_element.text
            )

            else ""

        )

        guid = (

            guid_element.text.strip()

            if (
                guid_element is not None
                and guid_element.text
            )

            else ""

        )

        date = (

            date_element.text.strip()

            if (
                date_element is not None
                and date_element.text
            )

            else ""

        )

        # ====================================================
        # ID DO TWEET
        # ====================================================

        search_text = (
            f"{guid} {link}"
        )

        match = re.search(
            r"/status/(\d{15,25})",
            search_text
        )

        if not match:
            continue

        tweet_id = match.group(1)

        # ====================================================
        # LINK
        # ====================================================

        if not link:

            link = (
                "https://x.com/HYPEX/status/"
                f"{tweet_id}"
            )

        # ====================================================
        # MEDIA
        # ====================================================

        media = extract_media(
            item
        )

        # ====================================================
        # ADICIONAR POST
        # ====================================================

        posts.append({

            "id": tweet_id,

            "title": title,

            "link": link,

            "date": date,

            "media": media

        })

    # ========================================================
    # REMOVER POSTS DUPLICADOS
    # ========================================================

    unique_posts = []

    seen_ids = set()

    for post in posts:

        if post["id"] in seen_ids:
            continue

        seen_ids.add(
            post["id"]
        )

        unique_posts.append(
            post
        )

    posts = unique_posts

    print(
        f"✅ {len(posts)} posts encontrados."
    )

    # ========================================================
    # MOSTRAR OS 5 MAIS RECENTES
    # ========================================================

    print("")
    print(
        "========== HYPEX ATUAL =========="
    )

    for post in posts[:5]:

        print(
            f"📝 {post['title'][:200]}"
        )

        print(
            f"🔗 {post['link']}"
        )

        print(
            f"🕒 {post['date']}"
        )

        print(
            f"📎 Media: {len(post['media'])}"
        )

        for media in post["media"]:

            print(
                f"   {media['type']}: "
                f"{media['url'][:200]}"
            )

        print(
            "--------------------------------"
        )

    print("")

    return posts


# ============================================================
# ENVIAR POST PARA O DISCORD
# ============================================================

async def send_post(post):

    # ========================================================
    # ESCOLHER CANAL
    # ========================================================

    if is_shop_post(
        post["title"]
    ):

        channel_id = SHOP_CHANNEL_ID

        embed_title = (
            "🛒 FORTNITE ITEM SHOP"
        )

    else:

        channel_id = NEWS_CHANNEL_ID

        embed_title = (
            "📰 HYPEX NEWS"
        )

    # ========================================================
    # OBTER CANAL
    # ========================================================

    channel = bot.get_channel(
        channel_id
    )

    if channel is None:

        try:

            channel = await bot.fetch_channel(
                channel_id
            )

        except Exception as error:

            print(
                f"❌ Não foi possível encontrar "
                f"o canal {channel_id}: "
                f"{error}"
            )

            return False

    # ========================================================
    # SEPARAR MEDIA
    # ========================================================

    media = post.get(
        "media",
        []
    )

    images = [

        item

        for item in media

        if item["type"] == "image"

    ]

    videos = [

        item

        for item in media

        if item["type"] == "video"

    ]

    # ========================================================
    # EMBED PRINCIPAL
    # ========================================================

    embed = discord.Embed(

        title=embed_title,

        description=post["title"],

        url=post["link"],

        color=discord.Color.blue()

    )

    embed.set_author(

        name="HYPEX",

        url="https://x.com/HYPEX"

    )

    # ========================================================
    # IMAGEM PRINCIPAL
    # ========================================================

    if images:

        try:

            embed.set_image(
                url=images[0]["url"]
            )

        except Exception as error:

            print(
                f"⚠️ Erro ao adicionar "
                f"imagem: {error}"
            )

    # ========================================================
    # FOOTER
    # ========================================================

    embed.set_footer(
        text="HYPEX • Fortnite News"
    )

    # ========================================================
    # ENVIAR EMBED
    # ========================================================

    try:

        await channel.send(
            embed=embed
        )

        # ====================================================
        # IMAGENS ADICIONAIS
        # ====================================================

        for extra_image in images[1:4]:

            try:

                extra_embed = discord.Embed(
                    url=post["link"]
                )

                extra_embed.set_image(
                    url=extra_image["url"]
                )

                await channel.send(
                    embed=extra_embed
                )

            except Exception as error:

                print(
                    f"⚠️ Erro ao enviar "
                    f"imagem adicional: "
                    f"{error}"
                )

        # ====================================================
        # VÍDEOS
        # ====================================================

        for video in videos[:2]:

            try:

                await channel.send(
                    video["url"]
                )

            except Exception as error:

                print(
                    f"⚠️ Erro ao enviar vídeo: "
                    f"{error}"
                )

        # ====================================================
        # LOG
        # ====================================================

        print(
            f"✅ Publicado: "
            f"{post['title'][:120]}"
        )

        if images:

            print(
                f"   🖼️ {len(images)} imagem(ns)"
            )

        if videos:

            print(
                f"   🎥 {len(videos)} vídeo(s)"
            )

        return True

    except Exception as error:

        print(
            f"❌ Erro ao enviar para Discord: "
            f"{type(error).__name__}: {error}"
        )

        return False


# ============================================================
# VERIFICAR HYPEX
# ============================================================

async def check_hypex():

    print(
        "🔎 A iniciar verificação HYPEX..."
    )

    posts = get_latest_posts()

    if not posts:

        print(
            "⚠️ Nenhum post encontrado."
        )

        return

    new_posts = 0

    # ========================================================
    # PUBLICAR DO MAIS ANTIGO PARA O MAIS RECENTE
    # ========================================================

    for post in reversed(posts):

        tweet_id = post["id"]

        # ----------------------------------------------------
        # EVITAR DUPLICADOS
        # ----------------------------------------------------

        if tweet_id in state["posted_ids"]:

            continue

        # ----------------------------------------------------
        # ENVIAR
        # ----------------------------------------------------

        success = await send_post(
            post
        )

        # ----------------------------------------------------
        # GUARDAR ID
        # ----------------------------------------------------

        if success:

            state["posted_ids"].append(
                tweet_id
            )

            # Guardar apenas os últimos 500
            state["posted_ids"] = (
                state["posted_ids"][-500:]
            )

            save_state(
                state
            )

            new_posts += 1

    print(
        f"✅ Verificação concluída. "
        f"{new_posts} novos posts."
    )


# ============================================================
# LOOP AUTOMÁTICO
# ============================================================

@tasks.loop(
    seconds=POLL_SECONDS
)
async def poll_hypex():

    try:

        await check_hypex()

    except Exception as error:

        print(
            f"❌ Erro no polling: "
            f"{type(error).__name__}: {error}"
        )


@poll_hypex.before_loop
async def before_poll():

    await bot.wait_until_ready()


# ============================================================
# COMANDO TESTSHOP
# ============================================================

@bot.command()
@commands.has_permissions(
    manage_guild=True
)
async def testshop(ctx):

    post = {

        "id": "TEST_SHOP",

        "title": (
            "Teste — Fortnite Item Shop"
        ),

        "link": "https://x.com/HYPEX",

        "date": "",

        "media": []

    }

    success = await send_post(
        post
    )

    if success:

        await ctx.send(
            "✅ Teste da Shop enviado!"
        )

    else:

        await ctx.send(
            "❌ Não foi possível "
            "enviar o teste."
        )


# ============================================================
# COMANDO TESTMEDIA
# ============================================================

@bot.command()
@commands.has_permissions(
    manage_guild=True
)
async def testmedia(ctx):

    await ctx.send(
        "🔎 A procurar o post mais recente "
        "do HYPEX..."
    )

    posts = get_latest_posts()

    if not posts:

        await ctx.send(
            "❌ Não consegui obter os "
            "posts do HYPEX."
        )

        return

    # Primeiro post = mais recente
    post = posts[0]

    # ========================================================
    # MOSTRAR NO CMD
    # ========================================================

    print("")
    print(
        "========== TESTE MEDIA =========="
    )

    print(
        f"📝 {post['title']}"
    )

    print(
        f"🔗 {post['link']}"
    )

    print(
        f"📎 Media encontrada: "
        f"{len(post['media'])}"
    )

    for media in post["media"]:

        print(
            f"   {media['type']}: "
            f"{media['url']}"
        )

    print(
        "=================================="
    )

    print("")

    # ========================================================
    # ENVIAR PARA DISCORD
    # ========================================================

    success = await send_post(
        post
    )

    if success:

        await ctx.send(
            "✅ **Teste concluído!**\n"
            "Enviei o post mais recente "
            "do HYPEX com a media encontrada."
        )

    else:

        await ctx.send(
            "❌ O Discord não conseguiu "
            "enviar o teste."
        )


# ============================================================
# BOT ONLINE
# ============================================================

@bot.event
async def on_ready():

    print(
        f"✅ Bot ligado como {bot.user}"
    )

    print(
        f"📡 Verificando HYPEX a cada "
        f"{POLL_SECONDS} segundos."
    )

    if not poll_hypex.is_running():

        poll_hypex.start()


# ============================================================
# VERIFICAÇÕES
# ============================================================

if not TOKEN:

    raise RuntimeError(
        "DISCORD_TOKEN não está definido "
        "no .env"
    )


if SHOP_CHANNEL_ID == 0:

    raise RuntimeError(
        "DISCORD_SHOP_CHANNEL_ID não está "
        "definido no .env"
    )


if NEWS_CHANNEL_ID == 0:

    raise RuntimeError(
        "DISCORD_NEWS_CHANNEL_ID não está "
        "definido no .env"
    )


# ============================================================
# INICIAR BOT
# ============================================================

bot.run(TOKEN)