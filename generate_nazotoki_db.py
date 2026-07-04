#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
謎解き用単語データベース自動生成スクリプト v2
wordfreq による日常語フィルタリング版

NLTK WordNet (OMW) から日本語名詞を取得し、
wordfreq の出現頻度で「日常的に知られている単語」だけを抽出して CSV を出力する。

実行前に以下のコマンドでライブラリをインストールしてください:
    pip install nltk pykakasi wordfreq mecab-python3 ipadic

※ wordfreq の日本語処理に MeCab が必要です。
※ MIN_ZIPF: 2.5（ラザニア 2.72 等も含む）。WordNet 未登録語は SUPPLEMENT_WORDS で補完。
"""

# ================================================================
# 必要なパッケージ (実行前にインストールしてください)
#   pip install nltk pykakasi wordfreq mecab-python3 ipadic
# ================================================================

import csv
import gzip
import os
import re
import sqlite3
import sys
import urllib.request
from collections import Counter

import nltk
from nltk.corpus import wordnet as wn
from pykakasi import kakasi
from wordfreq import zipf_frequency

# ── 設定 ────────────────────────────────────────────
OUTPUT_FILE = "nazotoki_auto.csv"

# wordfreq Zipf 頻度の下限
# 2.5 以上 = ラザニア(2.72)・マグカップ(3.32) 等も含む
# 3.5 以上 = より一般的な語のみ（約22,000語）
MIN_ZIPF = 2.5

# 最終出力する最大語数
MAX_WORDS = 45000

# カテゴリごとの採用上限
CATEGORY_QUOTAS = {
    "社会・文化":     25000,
    "道具・日用品":    8000,
    "人":            5000,
    "場所・地形":     2000,
    "生き物":         1200,
    "物質・素材":     1000,
    "自然・現象":     1000,
    "食べ物・飲み物":   900,
    "身体":           800,
    "その他":         600,
    "建物・施設":      400,
    "衣類":           400,
    "乗り物":         400,
}

MIN_READING_LEN = 2
MAX_READING_LEN = 12

WNJPN_URLS = [
    "https://github.com/bond-lab/wnja/releases/download/v1.1/wnjpn.db.gz",
    "http://compling.hss.ntu.edu.sg/wnja/data/wnjpn.db.gz",
]
WNJPN_DB = "wnjpn.db"

# ── WordNet 上位概念 → 日常カテゴリ マッピング ────────────
# 上にあるほど優先（具体的なカテゴリを先にチェック）
ANCHOR_SPECS = [
    # ── 人（organism より先に判定）──
    ("person.n.01",              "人"),
    # ── 生き物 ──
    ("bird.n.01",                "生き物"),
    ("fish.n.01",                "生き物"),
    ("insect.n.01",              "生き物"),
    ("mammal.n.01",              "生き物"),
    ("reptile.n.01",             "生き物"),
    ("amphibian.n.03",           "生き物"),
    ("invertebrate.n.01",        "生き物"),
    ("animal.n.01",              "生き物"),
    ("flower.n.01",              "生き物"),
    ("tree.n.01",                "生き物"),
    ("shrub.n.01",               "生き物"),
    ("fungus.n.01",              "生き物"),
    ("plant.n.02",               "生き物"),
    ("organism.n.01",            "生き物"),
    # ── 食べ物・飲み物 ──
    ("fruit.n.01",               "食べ物・飲み物"),
    ("vegetable.n.01",           "食べ物・飲み物"),
    ("beverage.n.01",            "食べ物・飲み物"),
    ("dish.n.02",                "食べ物・飲み物"),
    ("food.n.01",                "食べ物・飲み物"),
    ("food.n.02",                "食べ物・飲み物"),
    ("nutriment.n.01",           "食べ物・飲み物"),
    # ── 乗り物 ──
    ("vehicle.n.01",             "乗り物"),
    ("ship.n.01",                "乗り物"),
    ("aircraft.n.01",            "乗り物"),
    ("craft.n.02",               "乗り物"),
    # ── 衣類 ──
    ("clothing.n.01",            "衣類"),
    ("garment.n.01",             "衣類"),
    ("footwear.n.01",            "衣類"),
    ("headdress.n.01",           "衣類"),
    # ── 道具・日用品 ──
    ("musical_instrument.n.01",  "道具・日用品"),
    ("weapon.n.01",              "道具・日用品"),
    ("furniture.n.01",           "道具・日用品"),
    ("fabric.n.01",              "道具・日用品"),
    ("tool.n.01",                "道具・日用品"),
    ("utensil.n.01",             "道具・日用品"),
    ("container.n.01",           "道具・日用品"),
    ("device.n.01",              "道具・日用品"),
    ("machine.n.01",             "道具・日用品"),
    ("implement.n.01",           "道具・日用品"),
    ("game_equipment.n.01",      "道具・日用品"),
    ("sports_equipment.n.01",    "道具・日用品"),
    ("decoration.n.01",          "道具・日用品"),
    ("instrumentality.n.03",     "道具・日用品"),
    ("covering.n.02",            "道具・日用品"),
    ("plaything.n.01",           "道具・日用品"),
    ("commodity.n.01",           "道具・日用品"),
    ("artifact.n.01",            "道具・日用品"),
    # ── 建物・施設 ──
    ("building.n.01",            "建物・施設"),
    ("structure.n.01",           "建物・施設"),
    # ── 自然・現象 ──
    ("geological_formation.n.01","自然・現象"),
    ("celestial_body.n.01",      "自然・現象"),
    ("natural_object.n.01",      "自然・現象"),
    ("natural_phenomenon.n.01",  "自然・現象"),
    ("atmospheric_phenomenon.n.01", "自然・現象"),
    ("weather.n.01",             "自然・現象"),
    # ── 身体 ──
    ("body_part.n.01",           "身体"),
    ("organ.n.05",               "身体"),
    ("tissue.n.01",              "身体"),
    # ── 物質・素材 ──
    ("chemical_element.n.01",    "物質・素材"),
    ("mineral.n.01",             "物質・素材"),
    ("metal.n.01",               "物質・素材"),
    ("material.n.01",            "物質・素材"),
    ("substance.n.01",           "物質・素材"),
    ("substance.n.07",           "物質・素材"),
    # ── 場所・地形 ──
    ("body_of_water.n.01",       "場所・地形"),
    ("land.n.04",                "場所・地形"),
    ("region.n.01",              "場所・地形"),
    ("region.n.03",              "場所・地形"),
    ("location.n.01",            "場所・地形"),
    ("area.n.01",                "場所・地形"),
    # ── 社会・文化 ──
    ("event.n.01",               "社会・文化"),
    ("state.n.02",               "社会・文化"),
    ("act.n.02",                 "社会・文化"),
    ("activity.n.01",            "社会・文化"),
    ("process.n.06",             "社会・文化"),
    ("communication.n.02",       "社会・文化"),
    ("cognition.n.01",           "社会・文化"),
    ("feeling.n.01",             "社会・文化"),
    ("attribute.n.02",           "社会・文化"),
    ("measure.n.02",             "社会・文化"),
    ("time_period.n.01",         "社会・文化"),
    ("group.n.01",               "社会・文化"),
    ("social_group.n.01",        "社会・文化"),
    ("relation.n.01",            "社会・文化"),
    ("possession.n.02",          "社会・文化"),
    ("phenomenon.n.01",          "社会・文化"),
    # ── フォールバック ──
    ("physical_entity.n.01",     "その他"),
    ("abstraction.n.06",         "社会・文化"),
]

# 上位語の英語名→日本語サブカテゴリ変換マップ
_ENG_SUBCAT = {
    "acoustic device": "音響装置", "animal": "動物", "appendage": "付属物",
    "armor": "防具", "beverage": "飲料", "bird": "鳥類",
    "body of water": "水域", "body part": "身体部位",
    "building": "建築物", "cereal": "穀物", "chemical element": "元素",
    "citrus": "柑橘類", "clothing": "衣類", "color": "色",
    "commodity": "商品", "communication": "伝達", "compound": "化合物",
    "computer": "コンピュータ", "condiment": "調味料", "container": "容器",
    "conveyance": "運搬具", "cooking utensil": "調理器具", "cord": "紐",
    "covering": "被覆物", "cutting implement": "切断具",
    "dairy product": "乳製品", "decoration": "装飾", "device": "装置",
    "dish": "料理", "drug": "薬品", "electronic device": "電子装置",
    "fabric": "布地", "fastener": "留め具", "fiber": "繊維",
    "fish": "魚類", "flower": "花", "food": "食品",
    "footwear": "履物", "fruit": "果物", "fuel": "燃料",
    "fungus": "菌類", "furniture": "家具", "game": "遊戯",
    "game equipment": "遊具", "garment": "衣服",
    "geological formation": "地形", "hand tool": "手工具",
    "herb": "草本", "housing": "住宅", "implement": "器具",
    "insect": "昆虫", "instrument": "器具", "instrumentality": "道具類",
    "kitchen utensil": "台所用品", "lamp": "ランプ", "machine": "機械",
    "mammal": "哺乳類", "material": "素材", "mechanical device": "機械装置",
    "metal": "金属", "mineral": "鉱物", "mixture": "混合物",
    "motor vehicle": "自動車", "musical instrument": "楽器",
    "natural elevation": "自然地形", "natural object": "自然物",
    "nut": "ナッツ", "optical device": "光学装置", "organ": "器官",
    "organism": "生物", "paper": "紙", "person": "人",
    "plant": "植物", "plant organ": "植物器官", "plate": "皿",
    "protective covering": "保護材", "region": "地域",
    "reptile": "爬虫類", "room": "部屋", "sauce": "ソース",
    "seat": "座席", "shelter": "避難所", "ship": "船",
    "shoe": "靴", "shrub": "低木", "snake": "蛇", "solid": "固体",
    "source of illumination": "照明", "sports equipment": "運動用具",
    "stone": "石", "stringed instrument": "弦楽器",
    "structure": "構造物", "table": "テーブル", "textile": "織物",
    "tool": "道具", "tree": "樹木", "utensil": "用具",
    "vegetable": "野菜", "vehicle": "乗り物", "vessel": "容器",
    "watercraft": "船舶", "weapon": "武器", "weather": "天候",
    "wind instrument": "管楽器", "writing implement": "筆記具",
}


# ── 補完リスト（WordNet 未登録 or 定義・カテゴリを日常向けに上書き）──
# 各要素: word, main_cat, sub_cat, hint [, reading(省略可)]
SUPPLEMENT_WORDS = [
    # キッチン・家電
    ("ウォーターサーバー", "道具・日用品", "キッチン家電", "大きなボトルから冷水や温水を出してくれる家庭用の給水機"),
    ("ポット",           "道具・日用品", "調理器具",   "お湯を沸かしたりお茶をいれたりする金属やガラスの容器"),
    ("電気ケトル",       "道具・日用品", "キッチン家電", "電気で素早くお湯を沸かす小型のやかん"),
    ("食洗機",           "道具・日用品", "キッチン家電", "食器を自動で洗ってくれる台所の機械"),
    ("浄水器",           "道具・日用品", "キッチン家電", "水道水をろ過してきれいな水にする装置"),
    ("ホットプレート",   "道具・日用品", "調理器具",   "平らな加熱面で焼き物や鍋料理ができる調理器具"),
    ("トースター",       "道具・日用品", "キッチン家電", "パンをこんがり焼く小型の電気調理器具"),
    ("ミキサー",         "道具・日用品", "キッチン家電", "野菜や果物を細かく砕いたり混ぜたりする調理器具"),
    ("加湿器",           "道具・日用品", "家電",     "部屋の空気に水分を加えて乾燥を防ぐ機器"),
    ("除湿器",           "道具・日用品", "家電",     "部屋の湿気を取り除いてカビや不快を防ぐ機器"),
    ("扇風機",           "道具・日用品", "家電",     "羽根を回して風を送り、夏の暑さを和らげる機器"),
    ("ルームランナー",   "道具・日用品", "家電",     "室内で走ることができる運動用の機械"),
    # 食器・日用品
    ("マグカップ",       "道具・日用品", "食器",     "取っ手付きの筒形のコップで、温かい飲み物を入れる"),
    ("タンブラー",       "道具・日用品", "食器",     "取っ手のない筒形のコップ"),
    ("箸",               "道具・日用品", "食器",     "二本使って食べ物を挟み取る細長い棒"),
    ("茶碗",             "道具・日用品", "食器",     "ごはんを盛る小さめの深いお碗"),
    ("丼",               "道具・日用品", "食器",     "ラーメンや丼ものを盛る深くて平たいお碗"),
    ("キッチンペーパー", "道具・日用品", "日用品",   "台所で油や水を吸ったり拭いたりする使い捨て紙"),
    ("ラップ",           "道具・日用品", "日用品",   "食品を包んで保存する透明なフィルム"),
    ("アルミホイル",     "道具・日用品", "日用品",   "料理を包んだり覆ったりする薄いアルミのシート"),
    ("ゴミ袋",           "道具・日用品", "日用品",   "ごみを入れて捨てるためのビニールの袋"),
    ("ティッシュ",       "道具・日用品", "日用品",   "鼻をかんだり汚れを拭いたりする薄い紙"),
    ("洗剤",             "道具・日用品", "日用品",   "食器や洗濯物の汚れを落とすための液体や粉末"),
    ("ボディソープ",     "道具・日用品", "日用品",   "体を洗うときに使う泡立つ洗浄剤"),
    ("シャンプー",       "道具・日用品", "日用品",   "髪を洗うための泡立つ洗浄剤"),
    # 料理・食べ物
    ("ラザニア",         "食べ物・飲み物", "洋食",   "平たいパスタとミートソースとホワイトソースを重ねて焼いた料理"),
    ("グラタン",         "食べ物・飲み物", "洋食",   "ホワイトソースでソースを作り、チーズをのせてオーブンで焼いた料理"),
    ("ドリア",           "食べ物・飲み物", "洋食",   "ごはんの上にホワイトソースとチーズをのせて焼いた料理"),
    ("オムライス",       "食べ物・飲み物", "洋食",   "ケチャップライスを薄焼き卵で包んだ料理"),
    ("ハンバーグ",       "食べ物・飲み物", "洋食",   "挽き肉を丸く成形して焼いた洋風の肉料理"),
    ("餃子",             "食べ物・飲み物", "中華",   "ひき肉と野菜を包んだ皮を焼いたり蒸したりする料理"),
    ("春巻き",           "食べ物・飲み物", "中華",   "具材を薄い皮で巻いて揚げた中華の料理"),
    ("ポップコーン",     "食べ物・飲み物", "菓子",   "とうもろこしの粒を加熱してふくらませた軽いお菓子"),
    ("プリン",           "食べ物・飲み物", "菓子",   "卵と牛乳と砂糖で作るなめらかな洋菓子"),
    ("シュークリーム",   "食べ物・飲み物", "菓子",   "泡状の生地の中にクリームを入れた丸い洋菓子"),
    ("ドーナツ",         "食べ物・飲み物", "菓子",   "中央に穴のある丸い形をした揚げ菓子"),
    ("パンケーキ",       "食べ物・飲み物", "菓子",   "薄い円形の生地をフライパンで焼いた甘いパン"),
    ("ワッフル",         "食べ物・飲み物", "菓子",   "格子模様の型で焼いたふわふわの洋菓子"),
    ("タコス",           "食べ物・飲み物", "洋食",   "トウモロコシの薄い皮に具材をのせたメキシコの料理"),
    ("パエリア",         "食べ物・飲み物", "洋食",   "スペインの米と魚介や肉をサフランで炊いた料理"),
    ("リゾット",         "食べ物・飲み物", "洋食",   "イタリアのとろみのある炊き込み米料理"),
    ("カレー",           "食べ物・飲み物", "和食",   "スパイスを効かせたルーでごはんや具材を煮込んだ料理"),
    ("味噌汁",           "食べ物・飲み物", "和食",   "味噌を溶かしただし汁に豆腐やわかめなどを入れた汁物"),
    ("おにぎり",         "食べ物・飲み物", "和食",   "ごはんを三角形や丸形に握った携帯食"),
    ("弁当",             "食べ物・飲み物", "和食",   "ごはんとおかずを容器に詰めて持ち運べる食事"),
    # その他の日常語
    ("エアコン",         "道具・日用品", "家電",     "部屋の温度を冷やしたり暖めたりする空調機器"),
    ("洗濯機",           "道具・日用品", "家電",     "衣類を自動で洗う家庭用の機械"),
    ("掃除機",           "道具・日用品", "家電",     "床のほこりを吸い取って掃除する機械"),
    ("ドライヤー",       "道具・日用品", "家電",     "髪を乾かすために温かい風を出す機器"),
    ("アイロン",         "道具・日用品", "家電",     "衣類のしわを伸ばすために熱を当てる機器"),
    ("スマホ",           "道具・日用品", "電子機器", "電話やインターネットが使える手のひらサイズの端末"),
    ("パソコン",         "道具・日用品", "電子機器", "仕事や勉強に使う卓上型のコンピュータ"),
    ("充電器",           "道具・日用品", "電子機器", "スマホなどの電池に電気を供給する装置"),
    ("傘",               "道具・日用品", "雨具",     "雨や日差しを防ぐために頭の上に広げる道具"),
    ("財布",             "道具・日用品", "身の回り品", "お金やカードを入れて持ち歩く小さな入れ物"),
    ("鍵",               "道具・日用品", "身の回り品", "ドアやロッカーを開け閉めするための金属の道具"),
    ("メガネ",           "道具・日用品", "身の回り品", "レンズをはめ込んで視力を補う眼鏡"),
    ("時計",             "道具・日用品", "身の回り品", "現在の時刻を示す道具"),
    ("山",               "場所・地形",   "地形",     "地面が大きく盛り上がった自然の隆起"),
    ("川",               "場所・地形",   "地形",     "陸地を流れて海や湖に注ぐ水の流れ"),
    ("海",               "場所・地形",   "地形",     "広大な塩水が広がる地球表面の低い部分"),
    # SNS・インターネット（WordNet 未登録）
    ("ユーチューブ",     "社会・文化",   "SNS",      "動画をアップロードして世界中の人が視聴できるWebサービス"),
    ("YouTube",          "社会・文化",   "SNS",      "動画をアップロードして世界中の人が視聴できるWebサービス"),
    ("ユーチューバー",   "人",         "配信者",   "ユーチューブに動画を投稿して活動する人"),
    ("YouTuber",         "人",         "配信者",   "ユーチューブに動画を投稿して活動する人"),
    ("インフルエンサー", "人",         "SNS",      "SNSの影響力で多くの人の関心を集める人物"),
    ("配信者",           "人",         "SNS",      "インターネット上でライブや動画を配信する人"),
    ("動画配信",         "社会・文化",   "SNS",      "インターネットを通じて動画をリアルタイムまたは録画で届けること"),
    ("SNS",              "社会・文化",   "SNS",      "ソーシャルネットワーキングサービスの略で、人とつながるWebサービス"),
    ("インスタグラム",   "社会・文化",   "SNS",      "写真や短い動画を投稿して共有するSNSアプリ"),
    ("ツイッター",       "社会・文化",   "SNS",      "短い文章を投稿して情報をやり取りするSNSサービス"),
    ("ティックトック",   "社会・文化",   "SNS",      "短い動画を次々と見られるSNSアプリ"),
    # 流行語・現代文化（WordNet 未登録／謎解き向けヒント付き）
    ("推し活",           "社会・文化",   "流行語",   "好きな芸能人・アイドル・キャラクターを応援する活動"),
    ("推し",             "社会・文化",   "流行語",   "心から応援したいと思う人物やキャラクターのこと"),
    ("VTuber",           "人",         "配信者",   "仮想のキャラクター姿で動画配信を行うクリエイター"),
    ("推しカラー",       "社会・文化",   "流行語",   "応援している人物やグループを象徴する代表色"),
    ("推し曲",           "社会・文化",   "流行語",   "最も好きで何度も聴きたくなるお気に入りの曲"),
    ("リモートワーク",   "社会・文化",   "流行語",   "オフィスに出ずに自宅などから仕事をする働き方"),
    ("テレワーク",       "社会・文化",   "流行語",   "通信技術を使い、離れた場所から仕事を行う働き方"),
    ("ワーケーション",   "社会・文化",   "流行語",   "リゾート地などで休暇を楽しみながら仕事もするスタイル"),
    ("副業",             "社会・文化",   "流行語",   "本業のかたわらに別の仕事をして収入を得ること"),
    ("コワーキング",     "社会・文化",   "流行語",   "異なる会社の人が同じオフィスを共有して働くスペース"),
    ("サブスク",         "社会・文化",   "流行語",   "定額制でサービスや商品を継続利用すること"),
    ("キャッシュレス",   "社会・文化",   "流行語",   "現金を使わずカードやスマホで支払う決済方式"),
    ("ポイ活",           "社会・文化",   "流行語",   "ポイントを効率よく貯めることを目的にした活動"),
    ("セルフレジ",       "社会・文化",   "流行語",   "店員に頼らず自分で商品をスキャンして会計するレジ"),
    ("フードデリバリー", "社会・文化",   "流行語",   "スマホで注文した料理を自宅まで届けてもらうサービス"),
    ("ウーバーイーツ",   "社会・文化",   "流行語",   "スマホアプリで近くのレストランの料理を配達してもらえるサービス"),
    ("フリマアプリ",     "社会・文化",   "流行語",   "スマホで中古品を売り買いできるアプリケーション"),
    ("メルカリ",         "社会・文化",   "流行語",   "写真を撮って出品するだけで中古品を売れるフリマアプリ"),
    ("生成AI",           "社会・文化",   "流行語",   "人工知能が文章・画像・音声などを自動で作り出す技術"),
    ("ChatGPT",          "社会・文化",   "流行語",   "AIと会話しながら文章作成や質問応答ができるサービス"),
    ("メタバース",       "社会・文化",   "流行語",   "インターネット上に構築された仮想空間の世界"),
    ("オンライン会議",   "社会・文化",   "流行語",   "離れた場所の人と画面越しに打ち合わせをする方法"),
    ("Zoom",             "社会・文化",   "流行語",   "パソコンやスマホで多人数のビデオ会議ができるアプリ"),
    ("ライブ配信",       "社会・文化",   "流行語",   "インターネット上でリアルタイムに映像を届けること"),
    ("eスポーツ",        "社会・文化",   "流行語",   "ビデオゲームを競技として行い、勝敗を競うスポーツ"),
    ("グランピング",     "社会・文化",   "流行語",   "快適な設備を備えた場所で手軽に楽しむキャンプ"),
    ("断捨離",           "社会・文化",   "流行語",   "不要な物を捨てて生活をシンプルに整えること"),
    ("婚活",             "社会・文化",   "流行語",   "結婚相手を見つけるために積極的に活動すること"),
    ("マッチングアプリ", "社会・文化",   "流行語",   "スマホで恋人や友達を探せる出会い系アプリ"),
    ("猫カフェ",         "社会・文化",   "流行語",   "猫と触れ合いながら飲み物を楽しめるカフェ"),
    ("インスタ映え",     "社会・文化",   "流行語",   "SNSに投稿したくなるような見た目の良さ"),
    ("タピオカ",         "食べ物・飲み物", "流行語",   "黒い丸い粒が入った甘いミルクティーで一世を風靡した飲み物"),
    ("コンビニスイーツ", "食べ物・飲み物", "流行語",   "コンビニで手軽に買える高品質なケーキやスイーツ"),
    ("クラフトビール",   "食べ物・飲み物", "流行語",   "小規模醸造所が作る個性豊かなビール"),
    ("スマートスピーカー", "道具・日用品", "流行語",   "声で操作できるAIアシスタント付きのスピーカー"),
    ("NFT",              "社会・文化",   "流行語",   "デジタル作品の唯一性を証明するブロックチェーン技術"),
    ("エモい",           "社会・文化",   "流行語",   "感情に訴えかけるような雰囲気や情景を表す言葉"),
    ("コスプレ",         "社会・文化",   "流行語",   "漫画やアニメのキャラクターに扮装すること"),
    ("推し活グッズ",     "社会・文化",   "流行語",   "応援する人物の写真入りグッズやグッズ類"),
]

def setup_nltk():
    for pkg in ("wordnet", "omw-1.4"):
        nltk.download(pkg, quiet=True)


def download_wnjpn(dest_dir):
    """NICT 日本語 WordNet SQLite DB をダウンロード"""
    db_path = os.path.join(dest_dir, WNJPN_DB)
    if os.path.exists(db_path):
        return db_path
    gz_path = db_path + ".gz"
    for url in WNJPN_URLS:
        try:
            print(f"    ダウンロード中: {url}")
            urllib.request.urlretrieve(url, gz_path)
            with gzip.open(gz_path, "rb") as fi, open(db_path, "wb") as fo:
                fo.write(fi.read())
            if os.path.exists(gz_path):
                os.remove(gz_path)
            return db_path
        except Exception as e:
            print(f"    ※ 失敗 ({e})")
    return None


def load_jpn_definitions(db_path):
    """NICT DB から {(offset, pos): 日本語定義} を返す"""
    defs = {}
    if not db_path:
        return defs
    try:
        conn = sqlite3.connect(db_path)
        for synset_id, defn in conn.execute(
            "SELECT synset, def FROM synset_def WHERE lang='jpn'"
        ):
            parts = synset_id.split("-")
            if len(parts) == 2:
                defs[(int(parts[0]), parts[1])] = defn
        conn.close()
    except Exception as e:
        print(f"    ※ 日本語定義の読み込みに失敗: {e}")
    return defs


def build_anchors():
    anchors = []
    for name, cat in ANCHOR_SPECS:
        try:
            anchors.append((wn.synset(name), cat))
        except Exception:
            pass
    return anchors


def classify(synset, anchors):
    """(メインカテゴリ, サブカテゴリ) を返す"""
    ancestors = set()
    for path in synset.hypernym_paths():
        ancestors.update(path)

    main_cat = "その他"
    for anchor_ss, cat in anchors:
        if anchor_ss in ancestors or anchor_ss == synset:
            main_cat = cat
            break

    sub_cat = "一般"
    hypernyms = synset.hypernyms()
    if hypernyms:
        parent = hypernyms[0]
        try:
            jpn = parent.lemma_names("jpn")
        except Exception:
            jpn = []
        if jpn:
            sub_cat = jpn[0].lstrip("-")
        else:
            eng = parent.name().split(".")[0].replace("_", " ")
            sub_cat = _ENG_SUBCAT.get(eng, eng)
    return main_cat, sub_cat or "一般"


# ── 文字種フィルタ ──
_JP_CHAR = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]")
_ASCII_ONLY = re.compile(r"^[a-zA-Z0-9_\-\s.]+$")
_REJECT = set("_()[]{}「」・〜…\t\n")


def is_valid_word(word):
    if not word or len(word) > 10:
        return False
    if _ASCII_ONLY.match(word):
        return False
    if not _JP_CHAR.search(word):
        return False
    if _REJECT & set(word):
        return False
    return True


def kata_to_hira(text):
    buf = []
    for ch in text:
        cp = ord(ch)
        if 0x30A1 <= cp <= 0x30F6:
            buf.append(chr(cp - 0x60))
        else:
            buf.append(ch)
    return "".join(buf)


def get_reading(converter, word):
    items = converter.convert(word)
    raw = "".join(item["hira"] for item in items)
    return kata_to_hira(raw.replace(" ", "").replace("\u3000", ""))


def get_jpn_lemmas(synset):
    try:
        return synset.lemma_names("jpn")
    except Exception:
        return []


def build_supplement_entries(converter):
    """補完リストからエントリ dict のリストを生成する"""
    entries = []
    for item in SUPPLEMENT_WORDS:
        word, main_cat, sub_cat, hint = item[:4]
        reading = get_reading(converter, word)
        rlen = len(reading)
        if rlen < MIN_READING_LEN or rlen > MAX_READING_LEN:
            continue
        entries.append({
            "単語・フレーズ": word,
            "よみ": reading,
            "文字数": rlen,
            "メインカテゴリ": main_cat,
            "サブカテゴリ": sub_cat,
            "タイプ": "単語",
            "補足・ヒント": hint,
            "_zipf": zipf_frequency(word, "ja"),
            "_supplement": True,
        })
    return entries


# ================================================================
# メイン
# ================================================================

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 58)
    print("  謎解き用 日常単語データベース 自動生成 v2")
    print(f"  (Zipf >= {MIN_ZIPF} + 補完リスト {len(SUPPLEMENT_WORDS)} 語)")
    print("=" * 58)

    # 1. NLTK
    print("\n[1/5] NLTK データをダウンロード中...")
    setup_nltk()
    print("      完了")

    # 2. 日本語定義DB
    print("[2/5] 日本語定義データベースを準備中...")
    db_path = download_wnjpn(script_dir)
    jpn_defs = load_jpn_definitions(db_path)
    if jpn_defs:
        print(f"      {len(jpn_defs):,} 件の日本語定義を読み込みました")
    else:
        print("      ※ 英語定義で代替します")

    # 3. pykakasi
    print("[3/5] pykakasi を初期化中...")
    converter = kakasi()
    print("      完了")

    # 4. カテゴリ構築
    print("[4/5] カテゴリ定義を構築中...")
    anchors = build_anchors()
    print(f"      {len(anchors)} 個のアンカーを登録")

    # ── 5. 収集（頻度フィルター付き） ──
    print("[5/5] WordNet から日常語を収集中...")
    print(f"      (Zipf >= {MIN_ZIPF} → 上位 {MAX_WORDS:,} 語を採用)")

    # Phase A: 全単語を収集し、各単語の最初のsynset（最も一般的な語義）を採用
    word_best = {}
    total_checked = 0
    freq_rejected = 0
    synset_count = 0

    for synset in wn.all_synsets("n"):
        jpn_lemmas = get_jpn_lemmas(synset)
        if not jpn_lemmas:
            continue
        synset_count += 1

        for lemma in jpn_lemmas:
            if lemma in word_best:
                continue
            if not is_valid_word(lemma):
                continue

            total_checked += 1
            zipf = zipf_frequency(lemma, "ja")
            if zipf < MIN_ZIPF:
                freq_rejected += 1
                word_best[lemma] = None
                continue

            main_cat, sub_cat = classify(synset, anchors)
            word_best[lemma] = (main_cat, sub_cat, synset)

        if synset_count % 5000 == 0:
            passed = sum(1 for v in word_best.values() if v is not None)
            print(f"      ... {synset_count:,} synsets / {passed:,} 語通過")

    word_best = {k: v for k, v in word_best.items() if v is not None}
    print(f"      Phase A 完了: {len(word_best):,} 語が頻度フィルタ通過")

    # Phase C: カテゴリ枠で採用（各カテゴリ内で Zipf 上位を優先）
    from collections import defaultdict
    by_cat = defaultdict(list)
    for lemma, (cat, sub, ss) in word_best.items():
        by_cat[cat].append((zipf_frequency(lemma, "ja"), lemma))

    selected = []
    print("      Phase B: カテゴリ別に選択中...")
    for cat in sorted(by_cat, key=lambda c: -len(by_cat[c])):
        pool = sorted(by_cat[cat], reverse=True)
        quota = CATEGORY_QUOTAS.get(cat, 200)
        take = pool[:min(quota, len(pool))]
        selected.extend(w for _, w in take)
        print(f"        {cat:<12s}: {len(take):>4,} / {len(pool):>5,} 語")

    if len(selected) > MAX_WORDS:
        selected = selected[:MAX_WORDS]
    print(f"      選択合計: {len(selected):,} 語")

    # Phase D: 選択語の読み・定義を生成
    print("      Phase C: 読み・定義を生成中...")
    entries = []
    for i, lemma in enumerate(selected):
        main_cat, sub_cat, synset = word_best[lemma]

        reading = get_reading(converter, lemma)
        rlen = len(reading)
        if rlen < MIN_READING_LEN or rlen > MAX_READING_LEN:
            continue

        key = (synset.offset(), synset.pos())
        hint = jpn_defs.get(key, synset.definition())

        entries.append({
            "単語・フレーズ": lemma,
            "よみ": reading,
            "文字数": rlen,
            "メインカテゴリ": main_cat,
            "サブカテゴリ": sub_cat,
            "タイプ": "単語",
            "補足・ヒント": hint,
            "_zipf": zipf_frequency(lemma, "ja"),
        })

        if (i + 1) % 1000 == 0:
            print(f"        ... {i + 1:,} / {len(selected):,}")

    print(f"      最終エントリ (WordNet): {len(entries):,} 語")

    # Phase D: 補完リストをマージ（定義・カテゴリを日常向けに上書き）
    print("      Phase D: 補完リストをマージ中...")
    entry_map = {e["単語・フレーズ"]: e for e in entries}
    sup_added = sup_overridden = 0
    for sup in build_supplement_entries(converter):
        word = sup["単語・フレーズ"]
        if word in entry_map:
            sup_overridden += 1
        else:
            sup_added += 1
        entry_map[word] = sup
    entries = list(entry_map.values())
    print(f"        補完: 新規 {sup_added} 語 / 上書き {sup_overridden} 語")
    print(f"      合計: {len(entries):,} 語")

    # CSV 出力
    print("\nCSV ファイルを出力中...")
    output_path = os.path.join(script_dir, OUTPUT_FILE)
    fieldnames = [
        "単語・フレーズ", "よみ", "文字数",
        "メインカテゴリ", "サブカテゴリ", "タイプ", "補足・ヒント",
    ]

    sorted_entries = sorted(
        entries,
        key=lambda e: (e["メインカテゴリ"], e["サブカテゴリ"], e["文字数"]),
    )

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted_entries)

    # 集計
    cat_counts = Counter(e["メインカテゴリ"] for e in entries)
    char_counts = Counter(e["文字数"] for e in entries)
    jpn_count = sum(
        1 for e in entries
        if not all(c.isascii() for c in e["補足・ヒント"])
    )
    zipf_values = [e["_zipf"] for e in entries]

    print(f"\n{'=' * 58}")
    print(f"  出力完了: {output_path}")
    print(f"  総語数 : {len(entries):,}")
    print(f"  Zipf   : 平均 {sum(zipf_values)/len(zipf_values):.2f} / "
          f"最小 {min(zipf_values):.2f} / 最大 {max(zipf_values):.2f}")
    print(f"  定義   : 日本語 {jpn_count:,} / 英語 {len(entries)-jpn_count:,}")
    print()
    print("  【メインカテゴリ別】")
    for cat, cnt in cat_counts.most_common():
        print(f"    {cat:<10s}: {cnt:>5,} 語")
    print()
    print("  【文字数分布（よみ）】")
    for n in sorted(char_counts):
        bar = "#" * max(1, char_counts[n] // 5)
        print(f"    {n:2d} 文字: {char_counts[n]:>5,} 語  {bar}")
    print("=" * 58)


if __name__ == "__main__":
    main()
