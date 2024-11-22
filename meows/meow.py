import random
import re
from typing import Dict, List, Tuple, Optional

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf

CATS = {
    "happy": [
        "ฅ(＾・ω・＾ฅ)", "（＾・ω・＾✿）", "(=^･ω･^=)", "(^・x・^)",
        "(=｀ェ´=)", "（=´∇｀=）", "（Φ∇Φ）"
    ],
    "curious": [
        "^._.^", "(^･o･^)ﾉ", "(ΦωΦ)", "✿(=①ω①=)", "ฅ^•ﻌ•^ฅ",
        "₍˄·͈༝·͈˄*₎◞ ̑̑", "=^･ｪ･^="
    ],
    "sleepy": [
        "/ᐠ｡▿｡ᐟ\\*ᵖᵘʳʳ*", "✧/ᐠ-ꞈ-ᐟ\\", "/ᐠ –ꞈ –ᐟ\\",
        "(´͈ᵕ`͈)", "ᗢᵕᗢ"
    ],
    "grumpy": [
        "龴ↀ◡ↀ龴", "^ↀᴥↀ^", "(=；ェ；=)", "(=｀ω´=)"
    ],
    "playful": [
        "(=^･ｪ･^=))ﾉ彡☆", "(,,,)=(^.^)=(,,,)", "ᓚᘏᗢ"
    ]
}

CAT_RESPONSES = {
    r"\b(nya|nyaa|nyan)\b": {
        "happy": [
            ("Nya~!", "happy tail swish"),
            ("Nyaaaa♪", "playful bounce"),
            ("Nyan nyan!", "excited paw waves")
        ],
        "playful": [
            ("Nyanya!", "playful pounce"),
            ("Nyaaaa~", "rolls around happily"),
            ("Nya? Nyanya!", "playful head tilt")
        ]
    },
    r"\b(mrrp|mrp|brrrp)\b": {
        "curious": [
            ("Mrrrrp?", "curious head tilt"),
            ("Mrp!", "perked ears"),
            ("Brrrp?", "investigative sniff")
        ],
        "happy": [
            ("Mrrrrrrp!", "happy trill"),
            ("Brrrrrp~", "content chirp"),
            ("Mrrrp mrp!", "excited trill")
        ]
    },
    r"\b(purr|prrr)\b": {
        "happy": [
            ("*purrrrrrrr*", "loud content purring"),
            ("Prrrrrrr~", "deep happy purrs"),
            ("*rumbling purr*", "vibrating with happiness")
        ],
        "sleepy": [
            ("Prrrr...", "sleepy purring"),
            ("*soft purrs*", "gentle drowsy purring"),
            ("Prrr... zzz", "purring while dozing")
        ]
    },
    r"\b(now|quick|hurry)\b": {
        "tail": [
            ("Right meow!", "tail twitches impatiently"),
            ("Meow meow meow!", "swishes tail urgently"),
            ("*swish swish*", "tail flicking with anticipation")
        ]
    },
    r"\b(hi|hey|hello|howdy)\b": {
        "head": [
            ("Mrrp! Hi there!", "friendly head bump"),
            ("*perks up* Mrow~", "tilts head curiously"),
            ("Purrrr... hello!", "gentle head nuzzle")
        ]
    },
    r"\b(food|treat|hungry)\b": {
        "paw": [
            ("Food time?!", "paws at food bowl hopefully"),
            ("Treats?!", "extends paw politely"),
            ("*tap tap*", "gentle paw tap for attention")
        ]
    },
    r"\b(sleep|tired|bed|nap)\b": {
        "body": [
            ("*yawns* Meow too...", "curls into a tight ball"),
            ("Nap time...", "stretches out fully"),
            ("Perfect idea", "loafs contentedly")
        ]
    },
    r"\b(quiet|shh|hush)\b": {
        "vocal": [
            ("*soft mrrp*", "quiet purring"),
            ("*gentle meow*", "barely audible purr"),
            ("*whispered mew*", "subtle purring")
        ]
    },
    r"\b(yes|yeah|yep|yup)\b": {
        "happy": [
            ("Nyaaa~!", "happy purring"),
            ("Purrrr-cisely!", "content purring"),
            ("Mrow! Agreed!", "cheerful purring")
        ]
    },
    r"\b(no|nope|nah)\b": {
        "angry": [
            ("Hisssss!", "angry hissing"),
            ("MROWL!", "warning growl"),
            ("*angry cat noises*", "disgruntled growling")
        ],
        "grumpy": [
            ("Nyo.", "grumpy ear flick"),
            ("Nyot happening.", "turns away"),
            ("Meh.", "ignores completely")
        ]
    },
    r"\b(wow|whoa|omg|oh)\b": {
        "startled": [
            ("!!", "startled jump"),
            ("Mrow?!", "surprised leap"),
            ("*gasp*", "startled backwards hop")
        ],
        "interested": [
            ("Oho?", "perked ears and wide eyes"),
            ("Mew? What's this?", "alert and attentive"),
            ("*curious chirp*", "focused attention")
        ]
    },
    r"\b(meow)\b": {
        "vocal": [
            ("Meow! Meow!", "excited meowing back"),
            ("Mrrrrreow~", "enthusiastic meowing"),
            ("*meows back*", "happy meowing conversation")
        ],
        "playful": [
            ("Meow meow meow!", "playful bouncing"),
            ("Mrow? Meow!", "playful head tilt"),
            ("Meooooow~", "playful paw swatting")
        ]
    }
}


class Meow(commands.Cog):
    """
    A cat-themed bot that responds to certain words with consistent cat-like expressions!

    All commands are under the [p]meow group
    Example: [p]meow auto - Toggle automatic responses
    """

    def __init__(self, bot):
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, True)
        self.config.register_guild(
            auto_cat=False,
            enabled_triggers=list(CAT_RESPONSES.keys()),
            response_chance=0.3
        )
        self.cache = {}

    def get_random_cat(self, mood: str = None) -> str:
        """Get a random cat emoji, optionally of a specific mood"""
        if mood and mood in CATS:
            return random.choice(CATS[mood])
        return random.choice([cat for cats in CATS.values() for cat in cats])

    async def get_enabled_triggers(self, guild: discord.Guild) -> List[str]:
        """Get enabled triggers for a guild, updating cache if necessary"""
        if guild.id not in self.cache:
            self.cache[guild.id] = {
                "auto_cat": await self.config.guild(guild).auto_cat(),
                "triggers": await self.config.guild(guild).enabled_triggers()
            }
        return self.cache[guild.id]["triggers"]

    @commands.hybrid_group(invoke_without_command=True)
    async def meow(self, ctx: commands.Context):
        """Base command for all cat-related activities"""
        cat = self.get_random_cat("curious")
        await ctx.send(f"Meow! {cat} Use `{ctx.prefix}help meow` to see all my commands!")

    @meow.command(name="auto")
    @commands.guild_only()
    async def meow_auto(self, ctx: commands.Context):
        """Toggle automatic cat responses"""
        current = await self.config.guild(ctx.guild).auto_cat()
        await self.config.guild(ctx.guild).auto_cat.set(not current)
        if ctx.guild.id in self.cache:
            self.cache[ctx.guild.id]["auto_cat"] = not current
        cat = self.get_random_cat("happy" if not current else "grumpy")
        await ctx.send(f"Auto cat is now {'enabled' if not current else 'disabled'} {cat}")

    @meow.command(name="words")
    @commands.guild_only()
    async def meow_words(self, ctx: commands.Context):
        """List all words that the cat responds to"""
        enabled_triggers = await self.get_enabled_triggers(ctx.guild)
        trigger_words = []
        for pattern in enabled_triggers:
            words = pattern.replace('\\b', '').replace('\\', '').replace('(', '').replace(')', '')
            trigger_words.extend(words.split('|'))

        cat = self.get_random_cat("curious")
        pages = []
        chunks = [trigger_words[i:i + 20] for i in range(0, len(trigger_words), 20)]

        for i, chunk in enumerate(chunks, 1):
            message = f"I respond to these words {cat} (Page {i}/{len(chunks)})\n"
            message += "```\n" + "\n".join(chunk) + "\n```"
            if i == len(chunks):
                message += f"\nUse `{ctx.prefix}meow toggle <word>` to enable/disable specific triggers!"
                message += f"\nUse `{ctx.prefix}meow chance` to check or change response rate!"
            pages.append(message)

        if len(pages) == 1:
            await ctx.send(pages[0])
        else:
            await ctx.send_interactive(pages, box=False)

    @meow.command(name="toggle")
    @commands.guild_only()
    async def meow_toggle(self, ctx: commands.Context, word: str):
        """Toggle specific trigger words"""
        guild_triggers = await self.get_enabled_triggers(ctx.guild)

        full_pattern = next((p for p in CAT_RESPONSES.keys() if word in p), None)
        if not full_pattern:
            await ctx.send(f"Word '{word}' not found! Use `{ctx.prefix}meow words` to see available triggers.")
            return

        if full_pattern in guild_triggers:
            guild_triggers.remove(full_pattern)
            status = "disabled"
            mood = "grumpy"
        else:
            guild_triggers.append(full_pattern)
            status = "enabled"
            mood = "happy"

        await self.config.guild(ctx.guild).enabled_triggers.set(guild_triggers)
        if ctx.guild.id in self.cache:
            self.cache[ctx.guild.id]["triggers"] = guild_triggers

        cat = self.get_random_cat(mood)
        await ctx.send(f"Trigger word '{word}' is now {status} {cat}")

    @meow.command(name="expression")
    async def meow_expression(self, ctx: commands.Context, mood: Optional[str] = None):
        """
        Get a random cat expression
        Optional: Specify a mood (happy, curious, sleepy, grumpy, playful)
        """
        if mood and mood.lower() not in CATS:
            moods = ", ".join(CATS.keys())
            await ctx.send(f"Available moods: {moods}")
            return

        cat = self.get_random_cat(mood.lower() if mood else None)
        await ctx.send(cat)

    @meow.command(name="chance")
    @commands.guild_only()
    async def meow_chance(self, ctx: commands.Context, chance: Optional[float] = None):
        """
        Set the chance (0-1) that the cat will respond to triggers
        Example: [p]meow chance 0.5 for 50% response rate
        """
        if chance is None:
            current = await self.config.guild(ctx.guild).response_chance()
            await ctx.send(f"Current response chance: {current * 100}%")
            return

        if not 0 <= chance <= 1:
            await ctx.send("Chance must be between 0 and 1!")
            return

        await self.config.guild(ctx.guild).response_chance.set(chance)
        cat = self.get_random_cat("happy" if chance > 0 else "grumpy")
        await ctx.send(f"Response chance set to {chance * 100}% {cat}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        if message.guild.id not in self.cache:
            self.cache[message.guild.id] = {
                "auto_cat": await self.config.guild(message.guild).auto_cat(),
                "triggers": await self.config.guild(message.guild).enabled_triggers()
            }

        if not self.cache[message.guild.id]["auto_cat"]:
            return

        channel = message.channel
        if not channel.permissions_for(channel.guild.me).send_messages:
            return

        response_chance = await self.config.guild(message.guild).response_chance()
        enabled_triggers = self.cache[message.guild.id]["triggers"]

        for pattern in enabled_triggers:
            if pattern in CAT_RESPONSES and re.search(pattern, message.content, re.IGNORECASE):
                if random.random() <= response_chance:
                    behavior_type = random.choice(list(CAT_RESPONSES[pattern].keys()))
                    responses = CAT_RESPONSES[pattern][behavior_type]
                    response, reaction = random.choice(responses)
                    cat = self.get_random_cat(behavior_type)
                    await channel.send(f"{response} *{reaction}* {cat}")
                    break
