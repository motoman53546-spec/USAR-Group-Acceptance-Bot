import os
import discord
from discord import app_commands
from discord.ext import commands
import requests
from datetime import datetime

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

ROBLOX_API_KEY = os.getenv("ROBLOX_API_KEY")

GROUP_IDS = {
    "Military Police Corps": "33846212",
    "ASOC": "16997678",
    "AAC": "33333333",
    "TRADOC": "44444444",
    "FORSCOM": "55555555",
}

# Storage for server configurations (Guild ID -> Config Dict)
SERVER_CONFIGS = {}


class HighCommandReviewView(discord.ui.View):

  def __init__(
      self,
      username: str,
      group_name: str,
      rank: str,
      division: str,
      company: str,
      notes: str,
      proof_url: str,
      instructor: discord.User,
  ):
    super().__init__(timeout=None)
    self.username = username
    self.group_name = group_name
    self.rank = rank
    self.division = division
    self.company = company
    self.notes = notes
    self.proof_url = proof_url
    self.instructor = instructor

  @discord.ui.button(
      label="Approve & Send Request",
      style=discord.ButtonStyle.green,
      custom_id="hc_accept",
  )
  async def approve_request(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    config = SERVER_CONFIGS.get(interaction.guild_id, {})
    accepter_role_id = config.get("accepter_role")

    has_permission = interaction.user.guild_permissions.administrator
    if accepter_role_id and not has_permission:
      role = interaction.guild.get_role(accepter_role_id)
      if role and role in interaction.user.roles:
        has_permission = True

    if not has_permission:
      await interaction.response.send_message(
          "You do not have the required Group Accepter role or Administrator"
          " permissions to approve requests.",
          ephemeral=True,
      )
      return

    await interaction.response.defer()

    user_search_url = (
        f"https://users.roblox.com/v1/users/search?keyword={self.username}"
    )
    user_resp = requests.get(user_search_url)

    if user_resp.status_code != 200 or not user_resp.json().get("data"):
      await interaction.followup.send(
          f"Failed to find Roblox user `{self.username}` via search API.",
          ephemeral=True,
      )
      return

    user_data = user_resp.json()["data"][0]
    roblox_user_id = user_data["id"]

    group_id = GROUP_IDS.get(self.group_name)
    if not group_id:
      await interaction.followup.send(
          f"Invalid group mapping for `{self.group_name}`.", ephemeral=True
      )
      return

    requests_url = (
        f"https://apis.roblox.com/cloud/v2/groups/{group_id}/join-requests"
    )
    headers = {"x-api-key": ROBLOX_API_KEY}
    get_reqs = requests.get(requests_url, headers=headers)

    target_request_path = None
    if get_reqs.status_code == 200:
      for req in get_reqs.json().get("groupJoinRequests", []):
        if req.get("user", "").endswith(str(roblox_user_id)):
          target_request_path = req.get("path")
          break

    if not target_request_path:
      await interaction.followup.send(
          f"⚠️ **{self.username}** has not sent a manual join request in the"
          f" Roblox group (**{self.group_name}**) yet! Have them request to join"
          " on Roblox first, then click approve again.",
          ephemeral=True,
      )
      return

    accept_url = f"https://apis.roblox.com/cloud/v2/{target_request_path}:accept"
    accept_headers = {
        "x-api-key": ROBLOX_API_KEY,
        "Content-Type": "application/json",
    }
    response = requests.post(accept_url, headers=accept_headers, json={})

    for child in self.children:
      child.disabled = True

    try:
      await interaction.edit_original_response(view=self)
    except Exception:
      pass

    if response.status_code == 200:
      success_text = (
          f"Successfully approved and admitted **{self.username}** into"
          f" **{self.group_name}** ({self.rank} - {self.division} /"
          f" {self.company}) by {interaction.user.mention}!"
      )
      await interaction.followup.send(success_text, ephemeral=False)

      # Send a record into the designated Group Acceptance Audit Log channel
      acceptor_log_id = config.get("acceptor_log_channel")
      if acceptor_log_id:
        log_channel = interaction.guild.get_channel(acceptor_log_id)
        if log_channel:
          log_embed = discord.Embed(
              title="📋 Group Acceptance Audit Log (Approved)",
              color=discord.Color.green(),
              timestamp=datetime.utcnow(),
          )
          log_embed.add_field(
              name="Accepter", value=interaction.user.mention, inline=True
          )
          log_embed.add_field(
              name="Target User", value=self.username, inline=True
          )
          log_embed.add_field(
              name="Branch / Group", value=self.group_name, inline=True
          )
          log_embed.add_field(name="Target Rank", value=self.rank, inline=True)
          log_embed.add_field(
              name="Division / Company",
              value=f"{self.division} / {self.company}",
              inline=True,
          )
          log_embed.add_field(
              name="Action Status", value="Approved & Admitted", inline=True
          )
          log_embed.set_footer(
              text=f"Accepter ID: {interaction.user.id}",
              icon_url=interaction.user.display_avatar.url,
          )
          await log_channel.send(embed=log_embed)

    else:
      await interaction.followup.send(
          f"Failed to process Roblox group acceptance. Error:"
          f" `{response.text}`",
          ephemeral=True,
      )

  @discord.ui.button(
      label="Deny Request", style=discord.ButtonStyle.red, custom_id="hc_deny"
  )
  async def deny_request(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    config = SERVER_CONFIGS.get(interaction.guild_id, {})
    accepter_role_id = config.get("accepter_role")

    has_permission = interaction.user.guild_permissions.administrator
    if accepter_role_id and not has_permission:
      role = interaction.guild.get_role(accepter_role_id)
      if role and role in interaction.user.roles:
        has_permission = True

    if not has_permission:
      await interaction.response.send_message(
          "You do not have permission to manage requests.", ephemeral=True
      )
      return

    await interaction.response.defer()

    for child in self.children:
      child.disabled = True

    try:
      await interaction.edit_original_response(view=self)
    except Exception:
      pass

    deny_text = (
        f"Tryout log request for **{self.username}** was denied by"
        f" {interaction.user.mention}."
    )
    await interaction.followup.send(deny_text, ephemeral=False)

    # Log denial to acceptor audit log channel if configured
    acceptor_log_id = config.get("acceptor_log_channel")
    if acceptor_log_id:
      log_channel = interaction.guild.get_channel(acceptor_log_id)
      if log_channel:
        log_embed = discord.Embed(
            title="📋 Group Acceptance Audit Log (Denied)",
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )
        log_embed.add_field(
            name="Accepter", value=interaction.user.mention, inline=True
        )
        log_embed.add_field(
            name="Target User", value=self.username, inline=True
        )
        log_embed.add_field(
            name="Branch / Group", value=self.group_name, inline=True
        )
        log_embed.add_field(name="Action Status", value="Denied", inline=True)
        log_embed.set_footer(
            text=f"Accepter ID: {interaction.user.id}",
            icon_url=interaction.user.display_avatar.url,
        )
        await log_channel.send(embed=log_embed)


# Autocomplete for fetching real Roblox group ranks dynamically
async def rank_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
  branch_val = getattr(interaction.namespace, "branch", None)
  if not branch_val or branch_val not in GROUP_IDS:
    return []

  group_id = GROUP_IDS[branch_val]
  try:
    url = f"https://groups.roblox.com/v1/groups/{group_id}/roles"
    resp = requests.get(url, timeout=5)
    if resp.status_code == 200:
      roles = resp.json().get("roles", [])
      choices = [
          app_commands.Choice(name=role["name"], value=role["name"])
          for role in roles
          if current.lower() in role["name"].lower()
      ]
      return choices[:25]
  except Exception:
    pass
  return []


# Admin Setup Commands
@bot.tree.command(
    name="setup-requester-role",
    description="Set the role allowed to submit group requests (Admin only).",
)
@app_commands.default_permissions(administrator=True)
async def setup_requester_role(
    interaction: discord.Interaction, role: discord.Role
):
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["requester_role"] = role.id
  await interaction.response.send_message(
      f"✅ Group Requester role successfully set to {role.mention}.",
      ephemeral=True,
  )


@bot.tree.command(
    name="setup-accepter-role",
    description="Set the role allowed to approve/deny requests (Admin only).",
)
@app_commands.default_permissions(administrator=True)
async def setup_accepter_role(
    interaction: discord.Interaction, role: discord.Role
):
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["accepter_role"] = role.id
  await interaction.response.send_message(
      f"✅ Group Accepter role successfully set to {role.mention}.",
      ephemeral=True,
  )


@bot.tree.command(
    name="setup-request-channel",
    description=(
        "Set the group request logs channel where review embeds are posted"
        " (Admin only)."
    ),
)
@app_commands.default_permissions(administrator=True)
async def setup_request_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["request_channel"] = channel.id
  await interaction.response.send_message(
      f"✅ Group request logs channel successfully set to {channel.mention}.",
      ephemeral=True,
  )


@bot.tree.command(
    name="setup-grouprequest-channel",
    description=(
        "Set the channel where training staff must use /grouprequest (Admin"
        " only)."
    ),
)
@app_commands.default_permissions(administrator=True)
async def setup_grouprequest_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["grouprequest_channel"] = channel.id
  await interaction.response.send_message(
      f"✅ Training staff submission channel successfully set to"
      f" {channel.mention}.",
      ephemeral=True,
  )


@bot.tree.command(
    name="setup-acceptor-log-channel",
    description=(
        "Set the group acceptance audit logs channel for approvals/denials"
        " (Admin only)."
    ),
)
@app_commands.default_permissions(administrator=True)
async def setup_acceptor_log_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["acceptor_log_channel"] = channel.id
  await interaction.response.send_message(
      f"✅ Group acceptance audit log channel successfully set to"
      f" {channel.mention}.",
      ephemeral=True,
  )


# Standalone /rank command to check a user's role in a Roblox group
@bot.tree.command(
    name="rank", description="Check a user's current rank in a Roblox group."
)
@app_commands.choices(
    branch=[
        app_commands.Choice(
            name="Military Police Corps", value="Military Police Corps"
        ),
        app_commands.Choice(name="ASOC", value="ASOC"),
        app_commands.Choice(name="AAC", value="AAC"),
        app_commands.Choice(name="TRADOC", value="TRADOC"),
        app_commands.Choice(name="FORSCOM", value="FORSCOM"),
    ]
)
async def rank(
    interaction: discord.Interaction,
    username: str,
    branch: app_commands.Choice[str],
):
  await interaction.response.defer(ephemeral=True)

  user_search_url = (
      f"https://users.roblox.com/v1/users/search?keyword={username}"
  )
  user_resp = requests.get(user_search_url)

  if user_resp.status_code != 200 or not user_resp.json().get("data"):
    await interaction.followup.send(
        f"Failed to find Roblox user `{username}` via search API.",
        ephemeral=True,
    )
    return

  user_data = user_resp.json()["data"][0]
  roblox_user_id = user_data["id"]
  real_username = user_data["name"]

  group_id = GROUP_IDS.get(branch.name)

  # Fetch user's roles in groups
  groups_url = f"https://groups.roblox.com/v1/users/{roblox_user_id}/groups/roles"
  groups_resp = requests.get(groups_url)

  user_role_name = "Guest / Not in Group"
  user_rank_number = 0

  if groups_resp.status_code == 200:
    for g in groups_resp.json().get("data", []):
      if str(g.get("group", {}).get("id")) == str(group_id):
        user_role_name = g.get("role", {}).get("name", "Unknown")
        user_rank_number = g.get("role", {}).get("rank", 0)
        break

  embed = discord.Embed(
      title=f"Roblox Rank Lookup: {real_username}",
      color=discord.Color.blue(),
      timestamp=datetime.utcnow(),
  )
  embed.add_field(name="Group Branch", value=branch.name, inline=True)
  embed.add_field(name="Current Rank", value=user_role_name, inline=True)
  embed.add_field(name="Rank Number", value=str(user_rank_number), inline=True)
  embed.set_footer(text=f"Roblox User ID: {roblox_user_id}")

  await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(
    name="grouprequest",
    description="Submit a tryout completion log for review.",
)
@app_commands.choices(
    branch=[
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
    interaction: discord.Interaction,
    username: str,
    branch: app_commands.Choice[str],
    rank: str,
    division: str,
    company: str,
    notes: str,
    proof: discord.Attachment,
):
  config = SERVER_CONFIGS.get(interaction.guild_id, {})
  grouprequest_channel_id = config.get("grouprequest_channel")

  # Enforce channel restriction for submissions
  if grouprequest_channel_id and interaction.channel_id != grouprequest_channel_id:
    target_channel = interaction.guild.get_channel(grouprequest_channel_id)
    channel_mention = (
        target_channel.mention if target_channel else "the designated channel"
    )
    await interaction.response.send_message(
        f"❌ You can only use the `/grouprequest` command inside"
        f" {channel_mention}!",
        ephemeral=True,
    )
    return

  requester_role_id = config.get("requester_role")
  can_submit = interaction.user.guild_permissions.administrator
  if requester_role_id and not can_submit:
    role = interaction.guild.get_role(requester_role_id)
    if role and role in interaction.user.roles:
      can_submit = True

  if not can_submit:
    await interaction.response.send_message(
        "You do not have the required Group Requester role to submit tryout"
        " logs.",
        ephemeral=True,
    )
    return

  await interaction.response.defer(ephemeral=True)

  embed = discord.Embed(
      title="Tryout Proof / Group Acceptance Log",
      description="A new tryout result has been submitted for review.",
      color=discord.Color.dark_red(),
      timestamp=datetime.utcnow(),
  )
  embed.add_field(name="Attendee Username", value=username, inline=True)
  embed.add_field(name="Group Branch", value=branch.name, inline=True)
  embed.add_field(name="Target Rank", value=rank, inline=True)
  embed.add_field(name="Division", value=division, inline=True)
  embed.add_field(name="Company", value=company, inline=True)
  embed.add_field(name="Notes / Result", value=notes, inline=False)
  embed.add_field(name="Tested By", value=interaction.user.mention, inline=True)
  embed.set_image(url=proof.url)
  embed.set_footer(text="Waiting for High Command Approval...")

  view = HighCommandReviewView(
      username=username,
      group_name=branch.name,
      rank=rank,
      division=division,
      company=company,
      notes=notes,
      proof_url=proof.url,
      instructor=interaction.user,
  )

  # Send review embed to the configured Group Request Logs channel
  request_channel_id = config.get("request_channel")
  dest_channel = (
      interaction.guild.get_channel(request_channel_id)
      if request_channel_id
      else interaction.channel
  )

  await dest_channel.send(embed=embed, view=view)
  await interaction.followup.send(
      f"Your tryout request log has been successfully published to"
      f" {dest_channel.mention} for review!",
      ephemeral=True,
  )


@bot.event
async def on_ready():
  await bot.tree.sync()
  print(
      f"Logged in as {bot.user} - Live Roblox Ranks & Full Audit System Online!"
  )


bot.run(os.getenv("DISCORD_BOT_TOKEN"))