import os
import ssl
import discord
from redbot.core import commands, Config, app_commands
from discord.ui import Button, View
from typing import Union, Optional
from datetime import datetime
import asyncio
from aiohttp import web, ClientSession
import logging
import secrets
from collections import defaultdict
import socket
import base64
import urllib.parse
import hmac
import hashlib
import time
import random
import string


def generate_nonce(length=32):
    """Generate random nonce string"""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))


def sign_request(method, url, params, consumer_secret, token_secret=None):
    """Create OAuth 1.0a signature"""
    params = params.copy()
    params.pop('oauth_signature', None)
    param_string = '&'.join(
        f"{urllib.parse.quote(k, safe='')}"
        f"={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(params.items())
    )
    base_string = '&'.join([
        method.upper(),
        urllib.parse.quote(url, safe=''),
        urllib.parse.quote(param_string, safe='')
    ])
    signing_key = f"{urllib.parse.quote(consumer_secret, safe='')}&{urllib.parse.quote(token_secret or '', safe='')}"
    hashed = hmac.new(
        signing_key.encode('ascii'),
        base_string.encode('ascii'),
        hashlib.sha1
    )
    return base64.b64encode(hashed.digest()).decode('ascii')


class OAuthButton(Button):
    def __init__(self, oauth_url):
        super().__init__(label="Sign in with X", url=oauth_url, style=discord.ButtonStyle.url)


class XAuth(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=473444768378341377)
        self.pending_verifications = defaultdict(dict)
        self.web_app = None
        self.runner = None
        self.site = None
        self.session: Optional[ClientSession] = None

        bot.tree.add_command(app_commands.Command(
            name="verify",
            description="Connect your X account",
            callback=self.verify_slash
        ))


        self.SECURITY_HEADERS = {
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'Content-Security-Policy': "default-src 'self' 'unsafe-inline'",
            'X-XSS-Protection': '1; mode=block'
        }

        default_global = {
            "client_id": None,
            "client_secret": None,
            "callback_port": 443,
            "verified_role_id": None,
            "ssl_cert_path": None,
            "ssl_key_path": None,
            "domain": None
        }

        default_member = {
            "x_handle": None,
            "x_id": None,
            "verified_date": None
        }

        self.config.register_global(**default_global)
        self.config.register_member(**default_member)

        bot.loop.create_task(self.initialize())


    async def initialize(self):
        """Initialize the cog's aiohttp session and webhook server"""
        self.session = ClientSession()
        await self.setup_webhook_server()

    async def setup_webhook_server(self):
        """Set up the webhook server for OAuth callbacks"""
        try:
            base_port = 6123
            max_attempts = 8

            for port_offset in range(max_attempts):
                try:
                    port = base_port + port_offset
                    logging.info(f"Attempting to start internal server on port {port}")

                    @web.middleware
                    async def error_middleware(request, handler):
                        try:
                            return await handler(request)
                        except Exception as ex:
                            logging.error(f"An error occurred: {str(ex)}")
                            logging.exception(ex)
                            return web.Response(
                                text="Internal Server Error",
                                status=500,
                                headers=self.SECURITY_HEADERS
                            )

                    self.web_app = web.Application(middlewares=[error_middleware])
                    self.web_app.router.add_get('/callback', self.oauth_callback)
                    self.web_app.router.add_get('/', self.root_handler)

                    self.runner = web.AppRunner(self.web_app, access_log=logging.getLogger())
                    await self.runner.setup()

                    self.site = web.TCPSite(
                        self.runner,
                        'localhost',
                        port
                    )
                    await self.site.start()

                    logging.info(f"OAuth callback server started successfully on localhost:{port}")
                    logging.info(f"Make sure Nginx is configured to forward /callback to localhost:{port}")
                    break

                except OSError as e:
                    if e.errno == 98:  # Address already in use
                        if port_offset == max_attempts - 1:
                            raise  # Re-raise if we've tried all ports
                        continue  # Try next port
                    raise  # Re-raise if it's a different error

        except Exception as e:
            logging.error(f"Failed to start OAuth callback server: {e}")
            logging.exception(e)
            raise

    @staticmethod
    async def root_handler(request):
        """Handle root endpoint requests"""
        logging.info(f"Root request from: {request.remote}")
        return web.Response(text="OAuth server running")

    async def oauth_callback(self, request):
        """Handle OAuth callback requests"""
        logging.info("\n=== OAuth Callback Received ===")
        logging.info(f"Query Params: {dict(request.query)}")

        params = request.rel_url.query
        oauth_token = params.get('oauth_token')
        oauth_verifier = params.get('oauth_verifier')
        denied = params.get('denied')

        if denied:
            logging.error(f"OAuth access denied: {denied}")
            return web.Response(
                text="<html><body><h1>Authentication Cancelled</h1></body></html>",
                content_type='text/html',
                headers=self.SECURITY_HEADERS
            )

        if not oauth_token or not oauth_verifier:
            logging.error("Missing OAuth parameters")
            return web.Response(
                text="<html><body><h1>Error</h1><p>Missing parameters</p></body></html>",
                content_type='text/html',
                status=400,
                headers=self.SECURITY_HEADERS
            )

        found = False
        for state, verification in self.pending_verifications.items():
            if verification.get('oauth_token') == oauth_token:
                verification['oauth_verifier'] = oauth_verifier
                found = True
                break

        if not found:
            return web.Response(
                text="<html><body><h1>Error</h1><p>Invalid session</p></body></html>",
                content_type='text/html',
                status=400,
                headers=self.SECURITY_HEADERS
            )

        return web.Response(
            text="""
            <html>
            <head>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding-top: 50px; }
                    h1 { color: #1DA1F2; }
                    p { margin: 20px 0; }
                </style>
                <script>
                    setTimeout(function() { window.close(); }, 2000);
                </script>
            </head>
            <body>
                <h1>✓ Account Connected Successfully!</h1>
                <p>This window will close automatically...</p>
            </body>
            </html>
            """,
            content_type='text/html',
            headers=self.SECURITY_HEADERS
        )

    async def cog_unload(self):
        """Cleanup when cog is unloaded"""
        try:
            # Remove slash commands
            self.bot.tree.remove_command("verify")

            # Rest of cleanup
            if self.session:
                await self.session.close()
                self.session = None

            if self.site:
                await self.site.stop()
                self.site = None

            if self.runner:
                await self.runner.cleanup()
                self.runner = None

            self.pending_verifications.clear()
            logging.info("X Auth cog unloaded and cleaned up successfully")
        except Exception as e:
            logging.error(f"Error during X Auth cog cleanup: {e}")

    @staticmethod
    async def get_oauth_url(oauth_token: str) -> str:
        """Generate OAuth URL for X authentication"""
        return f"https://api.x.com/oauth/authenticate?oauth_token={oauth_token}"

    async def get_request_token(self) -> dict:
        """Get OAuth 1.0a request token"""
        try:
            client_id = await self.config.client_id()
            client_secret = await self.config.client_secret()

            url = 'https://api.x.com/oauth/request_token'

            timestamp = str(int(time.time()))
            nonce = generate_nonce()

            params = {
                'oauth_callback': 'oob',
                'oauth_consumer_key': client_id,
                'oauth_nonce': nonce,
                'oauth_signature_method': 'HMAC-SHA1',
                'oauth_timestamp': timestamp,
                'oauth_version': '1.0'
            }

            signature = sign_request('POST', url, params, client_secret)

            auth_header = 'OAuth ' + ', '.join(
                f'{k}="{urllib.parse.quote(str(v), safe="")}"'
                for k, v in sorted(params.items())
            ) + f', oauth_signature="{urllib.parse.quote(signature, safe="")}"'

            headers = {
                'Authorization': auth_header,
                'Content-Type': 'application/x-www-form-urlencoded',
            }

            async with self.session.post(url, headers=headers, data='') as resp:
                response_text = await resp.text()
                if resp.status != 200:
                    raise Exception(f"Failed to get request token: {response_text}")

                response_data = urllib.parse.parse_qs(response_text)
                return {
                    'oauth_token': response_data['oauth_token'][0],
                    'oauth_token_secret': response_data['oauth_token_secret'][0],
                }

        except Exception as e:
            logging.error(f"Error getting request token: {str(e)}")
            raise

    async def get_access_token(self, oauth_token: str, oauth_verifier: str, oauth_token_secret: str) -> dict:
        """Exchange OAuth verifier for access token"""
        try:
            client_id = await self.config.client_id()
            client_secret = await self.config.client_secret()

            url = 'https://api.x.com/oauth/access_token'
            oauth_params = {
                'oauth_consumer_key': client_id,
                'oauth_token': oauth_token,
                'oauth_verifier': oauth_verifier,
                'oauth_nonce': generate_nonce(),
                'oauth_signature_method': 'HMAC-SHA1',
                'oauth_timestamp': str(int(time.time())),
                'oauth_version': '1.0'
            }

            oauth_params['oauth_signature'] = sign_request(
                'POST',
                url,
                oauth_params,
                client_secret,
                oauth_token_secret
            )

            auth_header = 'OAuth ' + ', '.join(
                f'{k}="{urllib.parse.quote(str(v), safe="")}"'
                for k, v in sorted(oauth_params.items())
            )

            headers = {
                'Authorization': auth_header,
                'User-Agent': 'XAuth Discord Bot',
                'Host': 'api.x.com',
                'Accept': '*/*'
            }

            async with self.session.post(url, headers=headers) as resp:
                response_text = await resp.text()
                if resp.status != 200:
                    raise Exception(f"Failed to get access token: {response_text}")

                response_data = urllib.parse.parse_qs(response_text)
                return {
                    'oauth_token': response_data['oauth_token'][0],
                    'oauth_token_secret': response_data['oauth_token_secret'][0],
                    'user_id': response_data['user_id'][0],
                    'screen_name': response_data['screen_name'][0]
                }

        except Exception as e:
            logging.error(f"Error getting access token: {str(e)}")
            raise

    @commands.group(name="xauth")
    async def xauth(self, ctx):
        """X account connection management"""
        pass

    @commands.is_owner()
    @xauth.command()
    async def setup(self, ctx, client_id: str, client_secret: str, domain: str,
                    ssl_cert_path: str, ssl_key_path: str, port: int = 443):
        """Set up X API OAuth credentials and SSL configuration"""
        try:
            await ctx.message.delete()

            if not all([os.path.exists(ssl_cert_path), os.path.exists(ssl_key_path)]):
                return await ctx.send("❌ SSL certificate or key file not found")

            await self.config.client_id.set(client_id)
            await self.config.client_secret.set(client_secret)
            await self.config.domain.set(domain)
            await self.config.ssl_cert_path.set(ssl_cert_path)
            await self.config.ssl_key_path.set(ssl_key_path)
            await self.config.callback_port.set(port)

            # Obtain and store the Bearer Token
            bearer_token = await self.get_bearer_token()
            await self.config.bearer_token.set(bearer_token)

            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            await self.setup_webhook_server()

            success_msg = await ctx.send(
                "✅ X API OAuth credentials, SSL configuration, and Bearer Token updated successfully")
            await asyncio.sleep(5)
            await success_msg.delete()

        except discord.Forbidden:
            await ctx.send(
                "⚠️ Warning: Bot lacks permissions to delete messages. Please delete the setup command manually.")
        except Exception as e:
            error_msg = await ctx.send(f"❌ Error during setup: {str(e)}")
            await asyncio.sleep(5)
            await error_msg.delete()

    @commands.admin()
    @xauth.command()
    async def setrole(self, ctx, role: discord.Role):
        """Set verification role"""
        await self.config.verified_role_id.set(role.id)
        await ctx.send(f"Connected account role set to {role.name}")

    @xauth.command()
    async def verify(self, ctx):
        """Connect your X account"""
        if not await self.config.client_id() or not await self.config.client_secret():
            return await ctx.send("X API OAuth not configured. Please contact an admin.")

        if await self.config.member(ctx.author).x_handle():
            return await ctx.send("Your X account is already connected.")

        try:
            await ctx.send(f"{ctx.author.mention}, I've sent you a DM with instructions to connect your X account.")

            try:
                dm_channel = await ctx.author.create_dm()
            except discord.Forbidden:
                return await ctx.send(
                    f"{ctx.author.mention}, I couldn't send you a DM. Please check your privacy settings and try again.")

            token_data = await self.get_request_token()
            auth_url = await self.get_oauth_url(token_data['oauth_token'])

            embed = discord.Embed(
                title="Connect X Account",
                description=(
                    "1. Click the link below to connect your X account\n"
                    "2. Log in to X if needed\n"
                    "3. Authorize the application\n"
                    "4. You will see a PIN code. Copy it and send it back to me here."
                ),
                color=discord.Color.blue()
            )
            embed.add_field(name="Authorization Link", value=auth_url)

            await dm_channel.send(embed=embed)

            def check(m):
                return m.author == ctx.author and isinstance(m.channel, discord.DMChannel) and len(
                    m.content) == 7 and m.content.isdigit()

            try:
                pin_message = await self.bot.wait_for('message', check=check, timeout=300.0)
            except asyncio.TimeoutError:
                await dm_channel.send("Verification timed out. Please try again by using the command in the server.")
                return

            oauth_verifier = pin_message.content

            access_data = await self.get_access_token(
                token_data['oauth_token'],
                oauth_verifier,
                token_data['oauth_token_secret']
            )

            await self.config.member(ctx.author).x_handle.set(access_data['screen_name'])
            await self.config.member(ctx.author).x_id.set(access_data['user_id'])
            await self.config.member(ctx.author).verified_date.set(datetime.utcnow().isoformat())

            success_embed = discord.Embed(
                title="✅ Account Connected",
                description=f"Your X account @{access_data['screen_name']} has been connected successfully",
                color=discord.Color.green()
            )
            await dm_channel.send(embed=success_embed)

            verification_msg = await ctx.send(
                f"🎉 {ctx.author.mention}, your X account has been successfully connected!"
            )

            await asyncio.sleep(10)

            role_id = await self.config.verified_role_id()
            if role_id:
                role = ctx.guild.get_role(role_id)
                if role:
                    await ctx.author.add_roles(role)

        except Exception as e:
            logging.error(f"Error in verify command: {e}")
            await ctx.author.send(
                f"An error occurred: {str(e)}\nPlease try again later or contact an admin for assistance.")

    async def verify_slash(self, interaction: discord.Interaction):
        """Slash command version of verify"""
        if not await self.config.client_id() or not await self.config.client_secret():
            await interaction.response.send_message(
                "X API OAuth not configured. Please contact an admin.",
                ephemeral=True
            )
            return

        if await self.config.member(interaction.user).x_handle():
            await interaction.response.send_message(
                "Your X account is already connected.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.send_message(
                f"{interaction.user.mention}, I've sent you a DM with instructions to connect your X account.",
                ephemeral=True
            )

            try:
                dm_channel = await interaction.user.create_dm()
            except discord.Forbidden:
                await interaction.followup.send(
                    f"{interaction.user.mention}, I couldn't send you a DM. Please check your privacy settings and try again.",
                    ephemeral=True
                )
                return

            token_data = await self.get_request_token()
            auth_url = await self.get_oauth_url(token_data['oauth_token'])

            embed = discord.Embed(
                title="Connect X Account",
                description=(
                    "1. Click the link below to connect your X account\n"
                    "2. Log in to X if needed\n"
                    "3. Authorize the application\n"
                    "4. You will see a PIN code. Copy it and send it back to me here."
                ),
                color=discord.Color.blue()
            )
            embed.add_field(name="Authorization Link", value=auth_url)

            await dm_channel.send(embed=embed)

            def check(m):
                return m.author == interaction.user and isinstance(m.channel, discord.DMChannel) and len(
                    m.content) == 7 and m.content.isdigit()

            try:
                pin_message = await self.bot.wait_for('message', check=check, timeout=300.0)
            except asyncio.TimeoutError:
                await dm_channel.send("Verification timed out. Please try again by using the command in the server.")
                return

            oauth_verifier = pin_message.content

            access_data = await self.get_access_token(
                token_data['oauth_token'],
                oauth_verifier,
                token_data['oauth_token_secret']
            )

            await self.config.member(interaction.user).x_handle.set(access_data['screen_name'])
            await self.config.member(interaction.user).x_id.set(access_data['user_id'])
            await self.config.member(interaction.user).verified_date.set(datetime.utcnow().isoformat())

            success_embed = discord.Embed(
                title="✅ Account Connected",
                description=f"Your X account @{access_data['screen_name']} has been connected successfully",
                color=discord.Color.green()
            )
            await dm_channel.send(embed=success_embed)

            await interaction.followup.send(
                f"🎉 {interaction.user.mention}, your X account has been successfully connected!",
                ephemeral=True
            )

            await asyncio.sleep(10)

            role_id = await self.config.verified_role_id()
            if role_id and interaction.guild:
                role = interaction.guild.get_role(role_id)
                if role:
                    await interaction.user.add_roles(role)

        except Exception as e:
            logging.error(f"Error in verify slash command: {e}")
            await interaction.user.send(
                f"An error occurred: {str(e)}\nPlease try again later or contact an admin for assistance."
            )

    @commands.has_permissions(manage_roles=True)
    @xauth.command()
    async def whois(self, ctx, *, user: Union[discord.Member, str] = None):
        """Look up a user's X handle or Discord account"""
        if user is None:
            return await ctx.send_help()

        if isinstance(user, discord.Member):
            x_handle = await self.config.member(user).x_handle()
            if x_handle:
                try:
                    user_data = await self.make_authenticated_request('GET', f'/2/users/by/username/{x_handle}')
                    embed = discord.Embed(
                        title="User Lookup",
                        description=f"{user.mention}'s X handle is @{x_handle}",
                        color=discord.Color.blue()
                    )
                    embed.add_field(
                        name="X User ID",
                        value=user_data['data']['id']
                    )
                    embed.add_field(
                        name="Connected Date",
                        value=datetime.fromisoformat(await self.config.member(user).verified_date()).strftime(
                            "%Y-%m-%d %H:%M:%S UTC")
                    )
                    await ctx.send(embed=embed)
                except Exception as e:
                    await ctx.send(f"Error fetching X user data: {str(e)}")
            else:
                await ctx.send(f"{user.mention} has not connected their X account.")
        else:
            handle = str(user).lower().lstrip('@')
            found = False

            guild_data = await self.config.all_members(ctx.guild)
            for member_id, member_data in guild_data.items():
                if member_data.get('x_handle', '').lower() == handle:
                    member = ctx.guild.get_member(member_id)
                    if member:
                        found = True
                        try:
                            user_data = await self.make_authenticated_request('GET', f'/2/users/by/username/{handle}')
                            embed = discord.Embed(
                                title="Handle Lookup",
                                description=f"@{user} is connected to {member.mention}",
                                color=discord.Color.blue()
                            )
                            embed.add_field(
                                name="X User ID",
                                value=user_data['data']['id']
                            )
                            embed.add_field(
                                name="Connected Date",
                                value=datetime.fromisoformat(member_data['verified_date']).strftime(
                                    "%Y-%m-%d %H:%M:%S UTC")
                            )
                            await ctx.send(embed=embed)
                        except Exception as e:
                            await ctx.send(f"Error fetching X user data: {str(e)}")
                        break

            if not found:
                await ctx.send(f"No user found with X handle @{handle}")

    async def get_bearer_token(self):
        """Obtain an App-only Access Token (Bearer Token)"""
        try:
            client_id = await self.config.client_id()
            client_secret = await self.config.client_secret()

            # Encode the credentials
            credentials = f"{client_id}:{client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode('ascii')).decode('ascii')

            headers = {
                'Authorization': f'Basic {encoded_credentials}',
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
            }

            data = 'grant_type=client_credentials'

            async with self.session.post('https://api.x.com/oauth2/token', headers=headers, data=data) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to obtain Bearer Token: {await resp.text()}")

                response_data = await resp.json()
                return response_data['access_token']

        except Exception as e:
            logging.error(f"Error obtaining Bearer Token: {str(e)}")
            raise

    async def make_authenticated_request(self, method: str, endpoint: str, **kwargs):
        """Make an authenticated request to the X API using the Bearer Token"""
        try:
            bearer_token = await self.config.bearer_token()
            if not bearer_token:
                bearer_token = await self.get_bearer_token()
                await self.config.bearer_token.set(bearer_token)

            headers = {
                'Authorization': f'Bearer {bearer_token}',
                'User-Agent': 'XAuth Discord Bot',
            }
            headers.update(kwargs.get('headers', {}))
            kwargs['headers'] = headers

            url = f'https://api.x.com/{endpoint.lstrip("/")}'
            async with self.session.request(method, url, **kwargs) as resp:
                if resp.status == 401:
                    # Token might be expired, try to get a new one
                    bearer_token = await self.get_bearer_token()
                    await self.config.bearer_token.set(bearer_token)
                    headers['Authorization'] = f'Bearer {bearer_token}'
                    kwargs['headers'] = headers
                    async with self.session.request(method, url, **kwargs) as retry_resp:
                        return await retry_resp.json()
                return await resp.json()

        except Exception as e:
            logging.error(f"Error making authenticated request: {str(e)}")
            raise

    @commands.has_permissions(manage_roles=True)
    @xauth.command()
    async def unverify(self, ctx, member: discord.Member):
        """Disconnect a user's X account"""
        x_handle = await self.config.member(member).x_handle()
        if not x_handle:
            return await ctx.send(f"{member.mention} has not connected their X account.")

        await self.config.member(member).clear()

        role_id = await self.config.verified_role_id()
        if role_id:
            role = ctx.guild.get_role(role_id)
            if role and role in member.roles:
                await member.remove_roles(role)

        embed = discord.Embed(
            title="✅ Account Disconnected",
            description=f"{member.mention}'s X account (@{x_handle}) has been disconnected",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.is_owner()
    @xauth.command()
    async def clearall(self, ctx, confirmation: bool = False):
        """Clear all connection data (requires confirmation)"""
        if not confirmation:
            await ctx.send("⚠️ This will clear ALL X account connections. To confirm, use `=xauth clearall true`")
            return

        await self.config.clear_all()
        await ctx.send("✅ All X account connections have been cleared.")

    @commands.is_owner()
    @xauth.command()
    async def status(self, ctx):
        """Check the status of the X auth configuration"""
        client_id = await self.config.client_id()
        domain = await self.config.domain()
        port = await self.config.callback_port()
        role_id = await self.config.verified_role_id()

        embed = discord.Embed(
            title="X Auth Status",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="API Configuration",
            value=f"Client ID: {'✅ Set' if client_id else '❌ Not Set'}\n"
                  f"Client Secret: {'✅ Set' if await self.config.client_secret() else '❌ Not Set'}\n"
                  f"Domain: {domain or 'Not Set'}\n"
                  f"SSL: {'✅ Configured' if all([await self.config.ssl_cert_path(), await self.config.ssl_key_path()]) else '❌ Not Configured'}\n"
                  f"Callback Port: {port}",
            inline=False
        )

        if role_id:
            role = ctx.guild.get_role(role_id)
            embed.add_field(
                name="Connection Role",
                value=f"{role.mention if role else 'Invalid Role'} (ID: {role_id})",
                inline=False
            )
        else:
            embed.add_field(
                name="Connection Role",
                value="Not Set",
                inline=False
            )

        all_members = await self.config.all_members()
        total_verified = sum(1 for guild_data in all_members.values()
                             for member_data in guild_data.values()
                             if member_data.get('x_handle'))

        embed.add_field(
            name="Statistics",
            value=f"Total Connected Users: {total_verified}",
            inline=False
        )

        server_status = "✅ Running" if self.site else "❌ Not Running"
        embed.add_field(
            name="Server Status",
            value=f"Callback Server: {server_status}\n"
                  f"Active Connections: {len(self.pending_verifications)}",
            inline=False
        )

        await ctx.send(embed=embed)

    @commands.is_owner()
    @xauth.command()
    async def restart_server(self, ctx):
        """Restart the OAuth callback server"""
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()

            await self.setup_webhook_server()
            await ctx.send("✅ OAuth callback server restarted successfully")
        except Exception as e:
            await ctx.send(f"❌ Failed to restart server: {str(e)}")
