import os
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands
import requests

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

ROBLOX_API_KEY = os.getenv("ROBLOX_API_KEY")

COMMAND_IDS = {
    "Military Police Corps": "33846212",
    "ASOC": "16997678",
    "AAC": "33333333",
    "TRADOC": "44444444",
    "FORSCOM": "55555555",
}

SERVER_CONFIGS = {}


def check_accepter_permission(interaction: discord.Interaction) -> bool:
  config = SERVER_CONFIGS.get(interaction.guild_id, {})
  accepter_role_id = config.get("accepter_role")

  has_permission = interaction.user.guild_permissions.administrator
  if accepter_role_id and not has_permission:
    role = interaction.guild.get_role(accepter_role_id)
    if role and role in interaction.user.roles:
      has_permission = True
  return has_permission


class HighCommandReviewView(discord.ui.View):

  def __init__(
      self,
      username: str,
      command_name: str,
      division: str,
      rank: str,
      company: str,
      notes: str,
      proof_url: str,
      instructor: discord.User,
  ):
    super().__init__(timeout=None)
    self.username = username
    self.command_name = command_name
    self.division = division
    self.rank = rank
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
    if not check_accepter_permission(interaction):
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

    group_id = COMMAND_IDS.get(self.command_name)
    if not group_id:
      await interaction.followup.send(
          f"Invalid command mapping for `{self.command_name}`.", ephemeral=True
      )
      return

    headers = {"x-api-key": ROBLOX_API_KEY}

    roles_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/roles"
    roles_resp = requests.get(roles_url, headers=headers)
    target_role_id = None

    if roles_resp.status_code == 200:
      for r in roles_resp.json().get("groupRoles", []):
        if r.get("displayName", "").lower() == self.rank.lower():
          path_parts = r.get("path", "").split("/")
          target_role_id = path_parts[-1] if path_parts else None
          break

    if not target_role_id:
      v1_roles_url = f"https://groups.roblox.com/v1/groups/{group_id}/roles"
      v1_resp = requests.get(v1_roles_url)
      if v1_resp.status_code == 200:
        for r in v1_resp.json().get("roles", []):
          if r.get("name", "").lower() == self.rank.lower():
            target_role_id = str(r.get("id"))
            break

    member_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/memberships/{roblox_user_id}"
    member_resp = requests.get(member_url, headers=headers)

    if member_resp.status_code == 200:
      if target_role_id:
        patch_headers = {
            "x-api-key": ROBLOX_API_KEY,
            "Content-Type": "application/json",
        }
        update_resp = requests.patch(
            member_url,
            headers=patch_headers,
            json={"role": f"groups/{group_id}/roles/{target_role_id}"},
        )
        if update_resp.status_code != 200:
          await interaction.followup.send(
              f"Failed to update member rank on Roblox: `{update_resp.text}`",
              ephemeral=True,
          )
          return
    else:
      requests_url = (
          f"https://apis.roblox.com/cloud/v2/groups/{group_id}/join-requests"
      )
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
            f" Roblox group (**{self.command_name}**) yet! Have them request to"
            " join on Roblox first, then click approve again.",
            ephemeral=True,
        )
        return

      accept_url = (
          f"https://apis.roblox.com/cloud/v2/{target_request_path}:accept"
      )
      accept_headers = {
          "x-api-key": ROBLOX_API_KEY,
          "Content-Type": "application/json",
      }
      response = requests.post(accept_url, headers=accept_headers, json={})

      if response.status_code != 200:
        await interaction.followup.send(
            f"Failed to process Roblox group acceptance. Error:"
            f" `{response.text}`",
            ephemeral=True,
        )
        return

      if target_role_id:
        patch_headers = {
            "x-api-key": ROBLOX_API_KEY,
            "Content-Type": "application/json",
        }
        requests.patch(
            member_url,
            headers=patch_headers,
            json={"role": f"groups/{group_id}/roles/{target_role_id}"},
        )

    for child in self.children:
      child.disabled = True

    try:
      await interaction.edit_original_response(view=self)
    except Exception:
      pass

    success_text = (
        f"Successfully approved and admitted **{self.username}** into"
        f" **{self.command_name}** ({self.rank} - {self.division} /"
        f" {self.company}) by {interaction.user.mention}!"
    )
    await interaction.followup.send(success_text, ephemeral=False)

    config = SERVER_CONFIGS.get(interaction.guild_id, {})
    acceptor_log_id = config.get("acceptor_log_channel")
    if acceptor_log_id:
      log_channel = interaction.guild.get_channel(acceptor_log_id)
      if log_channel:
        log_embed = discord.Embed(
            title="📋 Group Acceptance Audit Log (Approved)",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        log_embed.add_field(
            name="Accepter", value=interaction.user.mention, inline=True
        )
        log_embed.add_field(
            name="Target User", value=self.username, inline=True
        )
        log_embed.add_field(name="Command", value=self.command_name, inline=True)
        log_embed.add_field(name="Assigned Rank", value=self.rank, inline=True)
        log_embed.add_field(
            name="Division / Company",
            value=f"{self.division} / {self.company}",
            inline=True,
        )
        await log_channel.send(embed=log_embed)

  @discord.ui.button(
      label="Deny Request", style=discord.ButtonStyle.red, custom_id="hc_deny"
  )
  async def deny_request(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not check_accepter_permission(interaction):
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

    await interaction.followup.send(
        f"Tryout log request for **{self.username}** was denied by"
        f" {interaction.user.mention}.",
        ephemeral=False,
    )


async def rank_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
  command_val = getattr(interaction.namespace, "command", None)
  if not command_val or command_val not in COMMAND_IDS:
    return []

  group_id = COMMAND_IDS[command_val]
  headers = {"x-api-key": ROBLOX_API_KEY} if ROBLOX_API_KEY else {}

  try:
    url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/roles"
    resp = requests.get(url, headers=headers, timeout=5)
    if resp.status_code == 200:
      roles = resp.json().get("groupRoles", [])
      choices = []
      for role in roles:
        name = role.get("displayName") or role.get("name")
        if name and current.lower() in name.lower():
          choices.append(app_commands.Choice(name=name, value=name))
      if choices:
        return choices[:25]
  except Exception:
    pass
  return []


@bot.tree.command(
    name="setup-requester-role", description="Set role allowed to request"
)
@app_commands.default_permissions(administrator=True)
async def setup_requester_role(
    interaction: discord.Interaction, role: discord.Role
):
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["requester_role"] = role.id
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
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["accepter_role"] = role.id
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
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["request_channel"] = channel.id
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
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["grouprequest_channel"] = channel.id
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
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["grouprequestlogs_channel"] = channel.id
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
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["acceptor_log_channel"] = channel.id
  await interaction.response.send_message(
      f"Acceptance log channel set to {channel.mention}", ephemeral=True
  )


@bot.tree.command(
    name="grouprequest",
    description="Submit a tryout completion log for review.",
)
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
    interaction: discord.Interaction,
    username: str,
    command: app_commands.Choice[str],
    division: str,
    rank: str,
    company: str,
    notes: str,
    proof: discord.Attachment,
):
  config = SERVER_CONFIGS.get(interaction.guild_id, {})
  grouprequest_channel_id = config.get("grouprequest_channel")

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

  review_embed = discord.Embed(
      title="Tryout Proof / Group Acceptance Review",
      description="A new tryout result has been submitted for High Command review.",
      color=discord.Color.dark_red(),
      timestamp=datetime.now(timezone.utc),
  )
  review_embed.add_field(name="Attendee Username", value=username, inline=True)
  review_embed.add_field(name="Command", value=command.name, inline=True)
  review_embed.add_field(name="Division", value=division, inline=True)
  review_embed.add_field(name="Target Rank", value=rank, inline=True)
  review_embed.add_field(name="Company", value=company, inline=True)
  review_embed.add_field(name="Notes / Result", value=notes, inline=False)
  review_embed.add_field(
      name="Requested By", value=interaction.user.mention, inline=True
  )
  review_embed.set_image(url=proof.url)
  review_embed.set_footer(text="Waiting for High Command Approval...")

  view = HighCommandReviewView(
      username=username,
      command_name=command.name,
      division=division,
      rank=rank,
      company=company,
      notes=notes,
      proof_url=proof.url,
      instructor=interaction.user,
  )

  request_channel_id = config.get("request_channel")
  dest_channel = (
      interaction.guild.get_channel(request_channel_id)
      if request_channel_id
      else interaction.channel
  )
  await dest_channel.send(embed=review_embed, view=view)

  grouprequestlogs_id = config.get("grouprequestlogs_channel")
  if grouprequestlogs_id:
    logs_channel = interaction.guild.get_channel(grouprequestlogs_id)
    if logs_channel:
      logs_embed = discord.Embed(
          title="📋 Group Request History Log",
          color=discord.Color.gold(),
          timestamp=datetime.now(timezone.utc),
      )
      logs_embed.add_field(
          name="Instructor / Staff", value=interaction.user.mention, inline=True
      )
      logs_embed.add_field(name="Attendee", value=username, inline=True)
      logs_embed.add_field(name="Command", value=command.name, inline=True)
      logs_embed.add_field(name="Division", value=division, inline=True)
      logs_embed.add_field(name="Target Rank", value=rank, inline=True)
      logs_embed.add_field(name="Company", value=company, inline=True)
      logs_embed.add_field(
          name="Submitted At",
          value=f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>",
          inline=False,
      )
      await logs_channel.send(embed=logs_embed)

  await interaction.followup.send(
      f"Your tryout request log has been successfully published to"
      f" {dest_channel.mention} for review!",
      ephemeral=True,
  )


# Direct Group Rank Update Command (Restricted to Accepters/Admins)
@bot.tree.command(
    name="changerank",
    description="Directly change a member's rank in a Roblox group.",
)
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
async def changerank(
    interaction: discord.Interaction,
    username: str,
    command: app_commands.Choice[str],
    rank: str,
):
  if not check_accepter_permission(interaction):
    await interaction.response.send_message(
        "❌ You do not have permission to change group ranks.", ephemeral=True
    )
    return

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

  group_id = COMMAND_IDS.get(command.name)
  if not group_id:
    await interaction.followup.send(
        f"Invalid command mapping for `{command.name}`.", ephemeral=True
    )
    return

  headers = {"x-api-key": ROBLOX_API_KEY}

  roles_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/roles"
  roles_resp = requests.get(roles_url, headers=headers)
  target_role_id = None

  if roles_resp.status_code == 200:
    for r in roles_resp.json().get("groupRoles", []):
      if r.get("displayName", "").lower() == rank.lower():
        path_parts = r.get("path", "").split("/")
        target_role_id = path_parts[-1] if path_parts else None
        break

  if not target_role_id:
    v1_roles_url = f"https://groups.roblox.com/v1/groups/{group_id}/roles"
    v1_resp = requests.get(v1_roles_url)
    if v1_resp.status_code == 200:
      for r in v1_resp.json().get("roles", []):
        if r.get("name", "").lower() == rank.lower():
          target_role_id = str(r.get("id"))
          break

  if not target_role_id:
    await interaction.followup.send(
        f"⚠️ Could not find exact Roblox role ID for rank `{rank}`.",
        ephemeral=True,
    )
    return

  member_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/memberships/{roblox_user_id}"
  patch_headers = {
      "x-api-key": ROBLOX_API_KEY,
      "Content-Type": "application/json",
  }

  # Check if member exists first; if not, check for join request and accept them
  member_resp = requests.get(member_url, headers=headers)
  if member_resp.status_code != 200:
    requests_url = (
        f"https://apis.roblox.com/cloud/v2/groups/{group_id}/join-requests"
    )
    get_reqs = requests.get(requests_url, headers=headers)

    target_request_path = None
    if get_reqs.status_code == 200:
      for req in get_reqs.json().get("groupJoinRequests", []):
        if req.get("user", "").endswith(str(roblox_user_id)):
          target_request_path = req.get("path")
          break

    if not target_request_path:
      await interaction.followup.send(
          f"⚠️ **{username}** is not in the group and has not sent a manual join request in **{command.name}** yet!",
          ephemeral=True,
      )
      return

    accept_url = f"https://apis.roblox.com/cloud/v2/{target_request_path}:accept"
    accept_headers = {
        "x-api-key": ROBLOX_API_KEY,
        "Content-Type": "application/json",
    }
    accept_resp = requests.post(accept_url, headers=accept_headers, json={})
    if accept_resp.status_code != 200:
      await interaction.followup.send(
          f"Failed to auto-accept join request: `{accept_resp.text}`",
          ephemeral=True,
      )
      return

  update_resp = requests.patch(
      member_url,
      headers=patch_headers,
      json={"role": f"groups/{group_id}/roles/{target_role_id}"},
  )

  if update_resp.status_code != 200:
    await interaction.followup.send(
        f"Failed to update rank on Roblox: `{update_resp.text}`",
        ephemeral=True,
    )
    return

  await interaction.followup.send(
      f"✅ Successfully updated **{username}'s** rank to **{rank}** in"
      f" **{command.name}**!",
      ephemeral=False,
  )


# Direct Group Kick / Demotion Command (Bypasses Open Cloud DELETE error)
@bot.tree.command(
    name="groupkick",
    description="Demote a member back to guest/unranked in a Roblox group.",
)
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
async def groupkick(
    interaction: discord.Interaction,
    username: str,
    command: app_commands.Choice[str],
):
  if not check_accepter_permission(interaction):
    await interaction.response.send_message(
        "❌ You do not have permission to kick/demote members from the group.",
        ephemeral=True,
    )
    return

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

  group_id = COMMAND_IDS.get(command.name)
  if not group_id:
    await interaction.followup.send(
        f"Invalid command mapping for `{command.name}`.", ephemeral=True
    )
    return

  headers = {"x-api-key": ROBLOX_API_KEY}

  roles_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/roles"
  roles_resp = requests.get(roles_url, headers=headers)
  lowest_role_id = None
  lowest_rank_val = 999

  if roles_resp.status_code == 200:
    for r in roles_resp.json().get("groupRoles", []):
      rank_val = r.get("rank", 999)
      if rank_val < lowest_rank_val:
        lowest_rank_val = rank_val
        path_parts = r.get("path", "").split("/")
        lowest_role_id = path_parts[-1] if path_parts else None

  if not lowest_role_id:
    v1_roles_url = f"https://groups.roblox.com/v1/groups/{group_id}/roles"
    v1_resp = requests.get(v1_roles_url)
    if v1_resp.status_code == 200:
      for r in v1_resp.json().get("roles", []):
        rank_val = r.get("rank", 999)
        if rank_val < lowest_rank_val:
          lowest_rank_val = rank_val
          lowest_role_id = str(r.get("id"))

  if not lowest_role_id:
    await interaction.followup.send(
        "❌ Could not determine the lowest guest role for this group.",
        ephemeral=True,
    )
    return

  member_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/memberships/{roblox_user_id}"
  patch_headers = {
      "x-api-key": ROBLOX_API_KEY,
      "Content-Type": "application/json",
  }
  update_resp = requests.patch(
      member_url,
      headers=patch_headers,
      json={"role": f"groups/{group_id}/roles/{lowest_role_id}"},
  )

  if update_resp.status_code != 200:
    await interaction.followup.send(
        f"Failed to reset member rank on Roblox: `{update_resp.text}`",
        ephemeral=True,
    )
    return

  await interaction.followup.send(
      f"✅ Successfully kicked/reset **{username}** back to guest rank in"
      f" **{command.name}**!",
      ephemeral=False,
  )


@bot.event
async def on_ready():
  await bot.tree.sync()
  print(
      f"Logged in as {bot.user} - Added /changerank and /groupkick commands"
      " with permission enforcement!"
  )


bot.run(os.getenv("DISCORD_BOT_TOKEN"))