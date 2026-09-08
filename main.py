import os
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Configuration mapping commands to Roblox Group IDs
COMMAND_IDS = {
    "Military Police Corps": "33846212",
    "ASOC": "16997678",
    "AAC": "33333333",
    "TRADOC": "44444444",
    "FORSCOM": "55555555",
}

# Channel and Role configuration storage (in-memory, use a database in production)
config_store = {
    "requester_role": None,
    "accepter_role": None,
    "request_channel": None,  # group-acceptance-requests
    "grouprequest_channel": None,  # group-request
    "grouprequestlogs_channel": None,  # group-request-logs
    "acceptor_log_channel": None,  # group-acceptance-logs
}


async def fetch_roblox_roles(group_id: str) -> list[dict]:
  url = f"https://groups.roblox.com/v1/groups/{group_id}/roles"
  async with aiohttp.ClientSession() as session:
    async with session.get(url) as resp:
      if resp.status == 200:
        data = await resp.json()
        return data.get("roles", [])
      return []


async def rank_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
  command_val = getattr(interaction.namespace, "command", None)
  if not command_val or command_val not in COMMAND_IDS:
    return []

  group_id = COMMAND_IDS[command_val]
  roles = await fetch_roblox_roles(group_id)

  choices = []
  for role in roles:
    role_name = role.get("name")
    if current.lower() in role_name.lower():
      choices.append(app_commands.Choice(name=role_name, value=role_name))
      if len(choices) >= 25:
        break
  return choices


@bot.event
async def on_ready():
  try:
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} command(s). Logged in as {bot.user}.")
  except Exception as e:
    print(f"Failed to sync commands: {e}")


# Setup Commands for Roles & Channels


@bot.tree.command(
    name="setup-requester-role", description="Set role allowed to request"
)
@app_commands.default_permissions(administrator=True)
async def setup_requester_role(
    interaction: discord.Interaction, role: discord.Role
):
  config_store["requester_role"] = role.id
  await interaction.response.send_message(
      f"Requester role set to {role.mention}", ephemeral=True
  )


@bot.tree.command(
    name="setup-accepter-role", description="Set role allowed to accept/deny"
)
@app_commands.default_permissions(administrator=True)
async def setup_accepter_role(
    interaction: discord.Interaction, role: discord.Role
):
  config_store["accepter_role"] = role.id
  await interaction.response.send_message(
      f"Accepter role set to {role.mention}", ephemeral=True
  )


@bot.tree.command(
    name="setup-request-channel",
    description="Set review embed channel (#group-acceptance-requests)",
)
@app_commands.default_permissions(administrator=True)
async def setup_request_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
  config_store["request_channel"] = channel.id
  await interaction.response.send_message(
      f"Review channel set to {channel.mention}", ephemeral=True
  )


@bot.tree.command(
    name="setup-grouprequest-channel",
    description="Set main request submission channel (#group-request)",
)
@app_commands.default_permissions(administrator=True)
async def setup_grouprequest_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
  config_store["grouprequest_channel"] = channel.id
  await interaction.response.send_message(
      f"Group request channel set to {channel.mention}", ephemeral=True
  )


@bot.tree.command(
    name="setup-grouprequestlogs-channel",
    description="Set instructor request logs channel (#group-request-logs)",
)
@app_commands.default_permissions(administrator=True)
async def setup_grouprequestlogs_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
  config_store["grouprequestlogs_channel"] = channel.id
  await interaction.response.send_message(
      f"Request logs channel set to {channel.mention}", ephemeral=True
  )


@bot.tree.command(
    name="setup-acceptor-log-channel",
    description="Set acceptance logs channel (#group-acceptance-logs)",
)
@app_commands.default_permissions(administrator=True)
async def setup_acceptor_log_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
  config_store["acceptor_log_channel"] = channel.id
  await interaction.response.send_message(
      f"Acceptance log channel set to {channel.mention}", ephemeral=True
  )


# Group Request Command


class GroupReviewModal(discord.ui.Modal, title="Group Rank Request"):
  roblox_username = discord.ui.TextInput(
      label="Roblox Username", placeholder="Enter username...", required=True
  )
  reason = discord.ui.TextInput(
      label="Reason / Notes",
      style=discord.TextStyle.paragraph,
      placeholder="Why is this rank requested?",
      required=True,
  )

  def __init__(self, command: str, rank: str):
    super().__init__()
    self.command = command
    self.rank = rank

  async def on_submit(self, interaction: discord.Interaction):
    req_channel_id = config_store.get("request_channel")
    log_channel_id = config_store.get("grouprequestlogs_channel")

    embed = discord.Embed(
        title="New Group Rank Request",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Instructor", value=interaction.user.mention, inline=True)
    embed.add_field(name="Command", value=self.command, inline=True)
    embed.add_field(name="Target Rank", value=self.rank, inline=True)
    embed.add_field(
        name="Roblox User", value=self.roblox_username.value, inline=False
    )
    embed.add_field(name="Reason", value=self.reason.value, inline=False)

    # Send to review channel
    if req_channel_id:
      req_channel = interaction.guild.get_channel(req_channel_id)
      if req_channel:
        view = ReviewActionView(interaction.user.id, self.roblox_username.value, self.rank)
        await req_channel.send(embed=embed, view=view)

    # Log the submission in group-request-logs
    if log_channel_id:
      log_channel = interaction.guild.get_channel(log_channel_id)
      if log_channel:
        log_embed = discord.Embed(
            title="Instructor Request Log",
            description=(
                f"**Instructor:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"**Command:** {self.command}\n"
                f"**Target Rank:** {self.rank}\n"
                f"**Roblox User:** `{self.roblox_username.value}`"
            ),
            color=discord.Color.dark_green(),
            timestamp=discord.utils.utcnow(),
        )
        await log_channel.send(embed=log_embed)

    await interaction.response.send_message(
        "Your group request has been submitted successfully!", ephemeral=True
    )


class ReviewActionView(discord.ui.View):

  def __init__(self, requester_id: int, target_user: str, target_rank: str):
    super().__init__(timeout=None)
    self.requester_id = requester_id
    self.target_user = target_user
    self.target_rank = target_rank

  @discord.ui.button(
      label="Accept", style=discord.ButtonStyle.green, custom_id="group_accept"
  )
  async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
    accepter_role_id = config_store.get("accepter_role")
    if accepter_role_id and not any(r.id == accepter_role_id for r in interaction.user.roles):
      await interaction.response.send_message(
          "You do not have permission to accept requests.", ephemeral=True
      )
      return

    accept_log_id = config_store.get("acceptor_log_channel")
    if accept_log_id:
      log_chan = interaction.guild.get_channel(accept_log_id)
      if log_chan:
        await log_chan.send(
            f"✅ Request for `{self.target_user}` (`{self.target_rank}`) accepted by {interaction.user.mention}."
        )

    for child in self.children:
      child.disabled = True
    await interaction.response.edit_message(view=self)
    await interaction.followup.send(
        f"Request accepted by {interaction.user.mention}.", ephemeral=True
    )

  @discord.ui.button(
      label="Deny", style=discord.ButtonStyle.danger, custom_id="group_deny"
  )
  async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
    accepter_role_id = config_store.get("accepter_role")
    if accepter_role_id and not any(r.id == accepter_role_id for r in interaction.user.roles):
      await interaction.response.send_message(
          "You do not have permission to deny requests.", ephemeral=True
      )
      return

    accept_log_id = config_store.get("acceptor_log_channel")
    if accept_log_id:
      log_chan = interaction.guild.get_channel(accept_log_id)
      if log_chan:
        await log_chan.send(
            f"❌ Request for `{self.target_user}` (`{self.target_rank}`) denied by {interaction.user.mention}."
        )

    for child in self.children:
      child.disabled = True
    await interaction.response.edit_message(view=self)
    await interaction.followup.send(
        f"Request denied by {interaction.user.mention}.", ephemeral=True
    )


@bot.tree.command(name="grouprequest", description="Submit a group rank request")
@app_commands.choices(
    command=[
        app_commands.Choice(
            name="Military Police Corps", value="Military Police Corps"
        ),
        app_commands.Choice(name="ASOC", value="ASOC"),
        app_commands.Choice(name="AAC", value="AAC"),
        app_commands.Choice(name="TRADOC", value="TRADOC"),
        app_commands.Choice(name="FORSCOM", value="FORSCOM"),
    ]
)
@app_commands.autocomplete(rank=rank_autocomplete)
async def grouprequest(
    interaction: discord.Interaction, command: str, rank: str
):
  req_role_id = config_store.get("requester_role")
  if req_role_id and not any(r.id == req_role_id for r in interaction.user.roles):
    await interaction.response.send_message(
        "You do not have the required requester role to use this command.",
        ephemeral=True,
    )
    return

  group_channel_id = config_store.get("grouprequest_channel")
  if group_channel_id and interaction.channel.id != group_channel_id:
    channel_mention = interaction.guild.get_channel(group_channel_id).mention
    await interaction.response.send_message(
        f"Please use this command in {channel_mention}.", ephemeral=True
    )
    return

  await interaction.response.send_modal(GroupReviewModal(command, rank))


# Replace with your bot token
bot.run("YOUR_BOT_TOKEN_HERE")