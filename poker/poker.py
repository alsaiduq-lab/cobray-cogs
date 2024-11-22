import discord
from redbot.core import commands, Config, checks
from .game import PokerGame
from .views import GetPlayersView, ConfirmView

class Poker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = []
        self.config = Config.get_conf(self, identifier=7345167902)
        self.config.register_guild(
            starting_chips=1000,
            min_players=2,
            max_players=8,
            small_blind=10,
            big_blind=20,
            do_image=True,
            use_threads=False
        )

    @commands.guild_only()
    @commands.command()
    async def poker(self, ctx, opponent: discord.Member=None):
        """Start a game of Texas Hold'em."""
        if [game for game in self.games if game.channel == ctx.channel]:
            return await ctx.send('A game is already running in this channel.')
        
        if opponent is None:
            view = GetPlayersView(ctx, await self.config.guild(ctx.guild).max_players())
            initial_message = await ctx.send(view.generate_message(), view=view)
        else:
            view = ConfirmView(opponent)
            initial_message = await ctx.send(f'{opponent.mention} You have been challenged to a game of Poker by {ctx.author.display_name}!', view=view)

        channel = ctx.channel
        if (
            await self.config.guild(ctx.guild).use_threads()
            and ctx.channel.permissions_for(ctx.guild.me).create_public_threads
            and ctx.channel.type is discord.ChannelType.text
        ):
            try:
                channel = await initial_message.create_thread(
                    name='Poker Game',
                    reason='Automated thread for Poker game.',
                )
            except discord.HTTPException:
                pass

        await view.wait()

        if opponent is None:
            players = view.players
        else:
            if not view.result:
                await channel.send(f'{opponent.display_name} does not want to play.')
                return
            players = [ctx.author, opponent]

        if len(players) < await self.config.guild(ctx.guild).min_players():
            return await channel.send('Not enough players to start.')

        game = PokerGame(ctx, channel, self, *players)
        self.games.append(game)
        await channel.send(f"Starting poker game with: {', '.join(p.display_name for p in players)}")

    @commands.guild_only()
    @checks.guildowner()
    @commands.command()
    async def pokerstop(self, ctx):
        """Stop the poker game in this channel."""
        wasGame = False
        for game in [g for g in self.games if g.channel == ctx.channel]:
            game._task.cancel()
            wasGame = True
        if wasGame:
            await ctx.send('The game was stopped successfully.')
        else:
            await ctx.send('There is no ongoing game in this channel.')
    
    @commands.command()
    async def pokerhand(self, ctx, channel: discord.TextChannel=None):
        """View your current hand from an ongoing game in your DMs."""
        if channel is None:
            channel = ctx.channel
        game = [game for game in self.games if game.channel.id == channel.id]
        if not game:
            return await ctx.send('There is no game in that channel.')
        game = game[0]
        if ctx.author not in game.players:
            return await ctx.send('You are not in that game.')
        await game.send_hand(ctx.author)

    def cog_unload(self):
        return [game._task.cancel() for game in self.games]

    async def red_delete_data_for_user(self, **kwargs):
        """Nothing to delete."""
        return
