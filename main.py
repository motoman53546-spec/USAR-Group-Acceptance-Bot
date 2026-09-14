from datetime import datetime, timezone
import os
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


async def fetch_security_background_check(
    discord_member: discord.Member,
    username: str,
    roblox_user_id: int,
    group_id: str,
) -> dict:
  """Performs an in-depth security evaluation resembling high-end bot frameworks."""
  data = {}

  # 1. Roblox Identity & Account Age Check
  try:
    user_info_url = f"https://users.roblox.com/v1/users/{roblox_user_id}"
    user_resp = requests.get(user_info_url, timeout=5)
    if user_resp.status_code == 200:
      u_json = user_resp.json()
      created_str = u_json.get("created", "")
      data["roblox_display"] = u_json.get("displayName", username)
      data["roblox_name"] = u_json.get("name", username)
      if created_str:
        dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - dt).days
        data["account_age_days"] = age_days
      else:
        data["account_age_days"] = 0
    else:
      data["account_age_days"] = 0
  except Exception:
    data["account_age_days"] = 0

  # Badges count check
  try:
    badges_url = f"https://badges.roblox.com/v1/users/{roblox_user_id}/badges?limit=10"
    b_resp = requests.get(badges_url, timeout=5)
    data["badges_earned"] = (
        len(b_resp.json().get("data", [])) if b_resp.status_code == 200 else 0
    )
  except Exception:
    data["badges_earned"] = 0

  # Alias history check
  try:
    aliases_url = f"https://users.roblox.com/v1/users/{roblox_user_id}/username-history"
    a_resp = requests.get(aliases_url, timeout=5)
    if a_resp.status_code == 200:
      history = a_resp.json().get("data", [])
      data["aliases"] = (
          [h.get("name") for h in history] if history else ["No recorded name changes"]
      )
    else:
      data["aliases"] = ["No recorded name changes"]
  except Exception:
    data["aliases"] = ["No recorded name changes"]

  # 2. Group Status & Rank Check
  try:
    group_roles_url = (
        f"https://groups.roblox.com/v1/users/{roblox_user_id}/groups/roles"
    )
    g_resp = requests.get(group_roles_url, timeout=5)
    current_rank = "Guest / Unranked"
    if g_resp.status_code == 200:
      for g in g_resp.json().get("data", []):
        if str(g.get("group", {}).get("id")) == str(group_id):
          current_rank = g.get("role", {}).get("name", "Member")
          break
    data["current_rank"] = current_rank
  except Exception:
    data["current_rank"] = "Unknown"

  data["total_xp"] = 0

  # 3. Discord Identity & Timestamps
  data["discord_user"] = str(discord_member)
  data["discord_created"] = discord_member.created_at
  data["discord_joined"] = (
      discord_member.joined_at if discord_member.joined_at else datetime.now(timezone.utc)
  )
  data["clearance_roles"] = [r.name for r in discord_member.roles if r.name != "@everyone"]

  risk = "GOOD (Low Risk)"
  if data["account_age_days"] < 30:
    risk = "CAUTION (New Account)"
  data["risk_status"] = risk

  return data


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

    # Fix Open Cloud v2 membership path resolution using memberships list
    member_list_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/memberships"
    member_resp = requests.get(
        member_list_url, headers=headers, params={"maxPageSize": 100}
    )

    target_membership_path = None
    if member_resp.status_code == 200:
      for member in member_resp.json().get("groupMemberships", []):
        if member.get("user", "").endswith(f"/{roblox_user_id}"):
          target_membership_path = member.get("path")
          break

    patch_headers = {
        "x-api-key": ROBLOX_API_KEY,
        "Content-Type": "application/json",
    }

    if target_membership_path:
      if target_role_id:
        update_url = f"https://apis.roblox.com/cloud/v2/{target_membership_path}"
        update_resp = requests.patch(
            update_url,
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

      # Re-fetch membership path post-acceptance to apply rank
      member_resp_retry = requests.get(
          member_list_url, headers=headers, params={"maxPageSize": 100}
      )
      if member_resp_retry.status_code == 200:
        for member in member_resp_retry.json().get("groupMemberships", []):
          if member.get("user", "").endswith(f"/{roblox_user_id}"):
            target_membership_path = member.get("path")
            break

      if target_membership_path and target_role_id:
        update_url = f"https://apis.roblox.com/cloud/v2/{target_membership_path}"
        requests.patch(
            update_url,
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

  user_search_url = (
      f"https://users.roblox.com/v1/users/search?keyword={username}"
  )
  user_resp = requests.get(user_search_url)

  if user_resp.status_code != 200 or not user_resp.json().get("data"):
    await interaction.followup.send(
        f"Failed to find Roblox user `{username}` via search API for security check.",
        ephemeral=True,
    )
    return

  user_data = user_resp.json()["data"][0]
  roblox_user_id = user_data["id"]
  group_id = COMMAND_IDS.get(command.name)

  bg = await fetch_security_background_check(
      interaction.user, username, roblox_user_id, group_id
  )

  created_years = round(bg["account_age_days"] / 365.25, 1)
  roles_str = (
      ", ".join([f"@{r}" for r in bg["clearance_roles"][:8]])
      if bg["clearance_roles"]
      else "@None"
  )
  aliases_formatted = (
      ", ".join(bg["aliases"]) if bg["aliases"] else "No recorded name changes"
  )
  server_join_unix = (
      int(bg["discord_joined"].timestamp()) if bg["discord_joined"] else int(datetime.now().timestamp())
  )
  discord_created_unix = (
      int(bg["discord_created"].timestamp()) if bg["discord_created"] else int(datetime.now().timestamp())
  )

  # Tryout proof / review info placed at the very top of the embed description
  security_text = (
      f"**Tryout Proof / Group Acceptance Review**\n"
      f"A new tryout result has been submitted for High Command review.\n\n"
      f"• **Attendee Username:** {username}\n"
      f"• **Command:** {command.name}\n"
      f"• **Division:** {division}\n"
      f"• **Target Rank:** {rank}\n"
      f"• **Company:** {company}\n"
      f"• **Notes / Result:** {notes}\n"
      f"• **Requested By:** {interaction.user.mention}\n\n"
      f"---------------------------------------------------\n\n"
      f"**BACKGROUND CHECK: {username} Security Evaluation**\n"
      f"**Status: {bg['risk_status']}**\n\n"
      f"**Roblox Identity**\n"
      f"• Profile: [{username}](https://www.roblox.com/users/{roblox_user_id}/profile)\n"
      f"• ID: `{roblox_user_id}`\n"
      f"• Account Age: ~{created_years} years ({bg['account_age_days']} days)\n"
      f"• Badges Earned: {bg['badges_earned']}\n\n"
      f"**Group Status**\n"
      f"• Current Rank: {bg['current_rank']}\n"
      f"• Total Recorded XP: {bg['total_xp']} XP\n\n"
      f"**Discord Identity**\n"
      f"• User: {interaction.user.mention}\n"
      f"• Account Created: <t:{discord_created_unix}:R>\n"
      f"• Server Join: <t:{server_join_unix}:R>\n\n"
      f"**Clearance & Roles**\n"
      f"{roles_str}\n\n"
      f"**Alias History**\n"
      f"{aliases_formatted}"
  )

  review_embed = discord.Embed(
      title=f"Tryout Proof / Group Acceptance Review",
      description=security_text,
      color=discord.Color.dark_red(),
      timestamp=datetime.now(timezone.utc),
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
      f"Your tryout request log with full security evaluation has been successfully published to"
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

  member_list_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/memberships"
  member_resp = requests.get(
      member_list_url, headers=headers, params={"maxPageSize": 100}
  )
  target_membership_path = None
  if member_resp.status_code == 200:
    for member in member_resp.json().get("groupMemberships", []):
      if member.get("user", "").endswith(f"/{roblox_user_id}"):
        target_membership_path = member.get("path")
        break

  patch_headers = {
      "x-api-key": ROBLOX_API_KEY,
      "Content-Type": "application/json",
  }

  if not target_membership_path:
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

    member_resp_retry = requests.get(
        member_list_url, headers=headers, params={"maxPageSize": 100}
    )
    if member_resp_retry.status_code == 200:
      for member in member_resp_retry.json().get("groupMemberships", []):
        if member.get("user", "").endswith(f"/{roblox_user_id}"):
          target_membership_path = member.get("path")
          break

  if not target_membership_path:
    await interaction.followup.send(
        "❌ Failed to locate membership resource path for the user.", ephemeral=True
    )
    return

  update_url = f"https://apis.roblox.com/cloud/v2/{target_membership_path}"
  update_resp = requests.patch(
      update_url,
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


# Direct Group Kick / Demotion Command
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

  member_list_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/memberships"
  member_resp = requests.get(
      member_list_url, headers=headers, params={"maxPageSize": 100}
  )
  target_membership_path = None
  if member_resp.status_code == 200:
    for member in member_resp.json().get("groupMemberships", []):
      if member.get("user", "").endswith(f"/{roblox_user_id}"):
        target_membership_path = member.get("path")
        break

  if not target_membership_path:
    await interaction.followup.send(
        f"❌ **{username}** is not an active member of this group.", ephemeral=True
    )
    return

  update_url = f"https://apis.roblox.com/cloud/v2/{target_membership_path}"
  patch_headers = {
      "x-api-key": ROBLOX_API_KEY,
      "Content-Type": "application/json",
  }
  update_resp = requests.patch(
      update_url,
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
      f"Logged in as {bot.user} - Reordered review embed so tryout proof/details"
      " appear at the top!"
  )


bot.run(os.getenv("DISCORD_BOT_TOKEN"))