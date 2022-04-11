# TabaBot
## Overview
TabaBot - another random bot. Main idea is message analysis: give some interesting info based on user's activity. Also there are music features, random trash commands and sending random phrases to chat.

`clever_quotes.txt` consists of phrases that bot can randomly send to chat. Each phrase separated by `;` symbol.

`replies.txt` contains phrases that bot can reply to specific user. Users separated by `\n`. User ID starts after `//` and separated from quotes by `->`. Phrases separated can be separated by `;` for quote with ping. `;№` and `;&` separate phrases without ping.

In `config.py` you can specify your token and some additional options.

## Requirements
python3 with dependencies from requirements.txt

Lavalink server for music features

***Optional***

nsfw-detector

selenium

webdriver_manager

## Launch
Start Lavalink server by `java -jar "filename"`

Start main.py by `py main.py`
