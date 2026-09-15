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

# Updated Group Structure with Main Group ID and Divisions
COMMAND_IDS = {
    "Military Police Corps": {
        "main_id": "33947594",
        "divisions": {
            "Military Police School": "48490266",
            "Judge Advocate General Corps": "61790730",
            "503rd Battalion": "35916795",
            "14th Battalion": "167855785",
            "Criminal Investigation Division": "73268634",
        },
    }
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


async def get_target_role_id(group_id: str, rank_name: str) -> str:
  headers = {"x-api-key": ROBLOX_API_KEY} if ROBLOX_API_KEY else {}
  roles_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/roles"
  roles_resp = requests.get(roles_url, headers=headers)
  target_role_id = None

  if roles_resp.status_code == 200:
    for r in roles_resp.json().get("groupRoles", []):
      if r.get("displayName", "").lower() == rank_name.lower():
        path_parts = r.get("path", "").split("/")
        target_role_id = path_parts[-1] if path_parts else None
        break

  if not target_role_id:
    v1_roles_url = f"https://groups.roblox.com/v1/groups/{group_id}/roles"
    v1_resp = requests.get(v1_roles_url)
    if v1_resp.status_code == 200:
      for r in v1_resp.json().get("roles", []):
        if r.get("name", "").lower() == rank_name.lower():
          target_role_id = str(r.get("id"))
          break
  return target_role_id


async def apply_group_rank(group_id: str, roblox_user_id: int, target_role_id: str) -> tuple[bool, str]:
  headers = {"x-api-key": ROBLOX_API_KEY} if ROBLOX_API_KEY else {}
  member_list_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/memberships"
  member_resp = requests.get(member_list_url, headers=headers, params={"maxPageSize": 100})

  target_membership_path = None
  if member_resp.status_code == 200:
    for member in member_resp.json().get("groupMemberships", []):
      if member.get("user", "").endswith(f"/{roblox_user_id}"):
        target_membership_path = member.get("path")
        break

  patch_headers = {
      "x-api-key": ROBLOX_API_KEY,
      "Content-Type": "application/json",
  } if ROBLOX_API_KEY else {"Content-Type": "application/json"}

  if not target_membership_path:
    requests_url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/join-requests"
    get_reqs = requests.get(requests_url, headers=headers)

    target_request_path = None
    if get_reqs.status_code == 200:
      for req in get_reqs.json().get("groupJoinRequests", []):
        if req.get("user", "").endswith(str(roblox_user_id)):
          target_request_path = req.get("path")
          break

    if not target_request_path:
      return False, "User is not in the group and has not sent a manual join request."

    accept_url = f"https://apis.roblox.com/cloud/v2/{target_request_path}:accept"
    accept_resp = requests.post(accept_url, headers=patch_headers, json={})
    if accept_resp.status_code != 200:
      return False, f"Failed to auto-accept join request: {accept_resp.text}"

    member_resp_retry = requests.get(member_list_url, headers=headers, params={"maxPageSize": 100})
    if member_resp_retry.status_code == 200:
      for member in member_resp_retry.json().get("groupMemberships", []):
        if member.get("user", "").endswith(f"/{roblox_user_id}"):
          target_membership_path = member.get("path")
          break

  if not target_membership_path:
    return False, "Failed to locate membership resource path."

  update_url = f"https://apis.roblox.com/cloud/v2/{target_membership_path}"
  update_resp = requests.patch(
      update_url,
      headers=patch_headers,
      json={"role": f"groups/{group_id}/roles/{target_role_id}"},
  )

  if update_resp.status_code != 200:
    return False, f"Failed to update rank: {update_resp.text}"

  return True, "Success"


class HighCommandReviewView(discord.ui.View):

  def __init__(
      self,
      username: str,
      command_name: str,
      division: str,
      main_rank: str,
      division_rank: str,
      company: str,
      notes: str,
      proof_url: str,
      instructor: discord.User,
  ):
    super().__init__(timeout=None)
    self.username = username
    self.command_name = command_name
    self.division = division
    self.main_rank = main_rank
    self.division_rank = division_rank
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
          "You do not have the required Group Accepter role or Administrator permissions to approve requests.",
          ephemeral=True,
      )
      return

    await interaction.response.defer()

    user_search_url = f"https://users.roblox.com/v1/users/search?keyword={self.username}"
    user_resp = requests.get(user_search_url)

    if user_resp.status_code != 200 or not user_resp.json().get("data"):
      await interaction.followup.send(
          f"Failed to find Roblox user `{self.username}` via search API.",
          ephemeral=True,
      )
      return

    user_data = user_resp.json()["data"][0]
    roblox_user_id = user_data["id"]

    command_info = COMMAND_IDS.get(self.command_name)
    if not command_info:
      await interaction.followup.send(
          f"Invalid command mapping for `{self.command_name}`.", ephemeral=True
      )
      return

    main_group_id = command_info["main_id"]
    division_id = command_info["divisions"].get(self.division)

    # 1. Update Main Group Rank
    main_role_id = await get_target_role_id(main_group_id, self.main_rank)
    if not main_role_id:
      await interaction.followup.send(
          f"⚠️ Could not find exact Roblox role ID for Main Group rank `{self.main_rank}`.",
          ephemeral=True,
      )
      return

    success, msg = await apply_group_rank(main_group_id, roblox_user_id, main_role_id)
    if not success:
      await interaction.followup.send(
          f"Failed to update Main Group rank: `{msg}`", ephemeral=True
      )
      return

    # 2. Update Division Group Rank (if division selected)
    if division_id and self.division_rank and self.division_rank != "None":
      div_role_id = await get_target_role_id(division_id, self.division_rank)
      if div_role_id:
        div_success, div_msg = await apply_group_rank(division_id, roblox_user_id, div_role_id)
        if not div_success:
          await interaction.followup.send(
              f"⚠️ Main group rank updated, but failed to update Division rank: `{div_msg}`",
              ephemeral=True,
          )
          return

    for child in self.children:
      child.disabled = True

    try:
      await interaction.edit_original_response(view=self)
    except Exception:
      pass

    success_text = (
        f"Successfully approved and admitted **{self.username}** into"
        f" **{self.command_name}** (Main Rank: {self.main_rank} | Division: {self.division} - {self.division_rank}) by {interaction.user.mention}!"
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
        log_embed.add_field(name="Accepter", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="Target User", value=self.username, inline=True)
        log_embed.add_field(name="Command", value=self.command_name, inline=True)
        log_embed.add_field(name="Main Rank", value=self.main_rank, inline=True)
        log_embed.add_field(name="Division & Rank", value=f"{self.division} ({self.division_rank})", inline=True)
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


async def main_rank_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
  command_val = getattr(interaction.namespace, "command", None)
  if not command_val or command_val not in COMMAND_IDS:
    return []

  group_id = COMMAND_IDS[command_val]["main_id"]
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


async def division_rank_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
  command_val = getattr(interaction.namespace, "command", None)
  division_val = getattr(interaction.namespace, "division", None)

  if not command_val or not division_val or command_val not in COMMAND_IDS:
    return []

  divisions = COMMAND_IDS[command_val]["divisions"]
  if division_val not in divisions:
    return []

  group_id = divisions[division_val]
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


@bot.tree.command(name="setup-requester-role", description="Set role allowed to request")
@app_commands.default_permissions(administrator=True)
async def setup_requester_role(interaction: discord.Interaction, role: discord.Role):
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["requester_role"] = role.id
  await interaction.response.send_message(f"Requester role set to {role.mention}", ephemeral=True)


@bot.tree.command(name="setup-accepter-role", description="Set role allowed to accept/deny")
@app_commands.default_permissions(administrator=True)
async def setup_accepter_role(interaction: discord.Interaction, role: discord.Role):
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["accepter_role"] = role.id
  await interaction.response.send_message(f"Accepter role set to {role.mention}", ephemeral=True)


@bot.tree.command(name="setup-request-channel", description="Set review embed channel")
@app_commands.default_permissions(administrator=True)
async def setup_request_channel(interaction: discord.Interaction, channel: discord.TextChannel):
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["request_channel"] = channel.id
  await interaction.response.send_message(f"Review channel set to {channel.mention}", ephemeral=True)


@bot.tree.command(name="setup-grouprequest-channel", description="Set main request submission channel")
@app_commands.default_permissions(administrator=True)
async def setup_grouprequest_channel(interaction: discord.Interaction, channel: discord.TextChannel):
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["grouprequest_channel"] = channel.id
  await interaction.response.send_message(f"Group request channel set to {channel.mention}", ephemeral=True)


@bot.tree.command(name="setup-grouprequestlogs-channel", description="Set instructor request logs channel")
@app_commands.default_permissions(administrator=True)
async def setup_grouprequestlogs_channel(interaction: discord.Interaction, channel: discord.TextChannel):
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["grouprequestlogs_channel"] = channel.id
  await interaction.response.send_message(f"Request logs channel set to {channel.mention}", ephemeral=True)


@bot.tree.command(name="setup-acceptor-log-channel", description="Set acceptance logs channel")
@app_commands.default_permissions(administrator=True)
async def setup_acceptor_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
  if interaction.guild_id not in SERVER_CONFIGS:
    SERVER_CONFIGS[interaction.guild_id] = {}
  SERVER_CONFIGS[interaction.guild_id]["acceptor_log_channel"] = channel.id
  await interaction.response.send_message(f"Acceptance log channel set to {channel.mention}", ephemeral=True)


@bot.tree.command(
    name="grouprequest",
    description="Submit a tryout completion log for review.",
)
@app_commands.choices(
    command=[
        app_commands.Choice(name="Military Police Corps", value="Military Police Corps"),
    ],
    division=[
        app_commands.Choice(name="Military Police School", value="Military Police School"),
        app_commands.Choice(name="Judge Advocate General Corps", value="Judge Advocate General Corps"),
        app_commands.Choice(name="503rd Battalion", value="503rd Battalion"),
        app_commands.Choice(name="14th Battalion", value="14th Battalion"),
        app_commands.Choice(name="Criminal Investigation Division", value="Criminal Investigation Division"),
    ],
)
@app_commands.autocomplete(
    main_rank=main_rank_autocomplete,
    division_rank=division_rank_autocomplete,
)
async def grouprequest(
    interaction: discord.Interaction,
    username: str,
    discord_id: str,
    command: app_commands.Choice[str],
    division: app_commands.Choice[str],
    main_rank: str,
    division_rank: str,
    company: str,
    notes: str,
    proof: discord.Attachment,
):
  config = SERVER_CONFIGS.get(interaction.guild_id, {})
  grouprequest_channel_id = config.get("grouprequest_channel")

  if grouprequest_channel_id and interaction.channel_id != grouprequest_channel_id:
    target_channel = interaction.guild.get_channel(grouprequest_channel_id)
    channel_mention = target_channel.mention if target_channel else "the designated channel"
    await interaction.response.send_message(
        f"❌ You can only use the `/grouprequest` command inside {channel_mention}!",
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
        "You do not have the required Group Requester role to submit tryout logs.",
        ephemeral=True,
    )
    return

  await interaction.response.defer(ephemeral=True)

  # Parse the Discord ID string and fetch the member/user
  try:
    user_id_int = int(discord_id.strip())
    fetched_member = interaction.guild.get_member(user_id_int)
    if not fetched_member:
      fetched_member = await bot.fetch_user(user_id_int)
  except ValueError:
    fetched_member = None

  if not fetched_member:
    await interaction.followup.send(
        f"❌ Could not find a Discord user matching ID `{discord_id}`. Please check the ID and try again.",
        ephemeral=True,
    )
    return

  user_search_url = f"https://users.roblox.com/v1/users/search?keyword={username}"
  user_resp = requests.get(user_search_url)

  if user_resp.status_code != 200 or not user_resp.json().get("data"):
    await interaction.followup.send(
        f"Failed to find Roblox user `{username}` via search API for security check.",
        ephemeral=True,
    )
    return

  user_data = user_resp.json()["data"][0]
  roblox_user_id = user_data["id"]
  group_id = COMMAND_IDS[command.name]["main_id"]

  bg = await fetch_security_background_check(
      fetched_member, username, roblox_user_id, group_id
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

  security_text = (
      f"**Tryout Proof / Group Acceptance Review**\n"
      f"A new tryout result has been submitted for High Command review.\n\n"
      f"• **Attendee Username:** {username}\n"
      f"• **Command:** {command.name}\n"
      f"• **Division:** {division.name}\n"
      f"• **Main Group Rank:** {main_rank}\n"
      f"• **Division Group Rank:** {division_rank}\n"
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
      f"• User: {fetched_member.mention}\n"
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
      division=division.name,
      main_rank=main_rank,
      division_rank=division_rank,
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
      logs_embed.add_field(name="Instructor / Staff", value=interaction.user.mention, inline=True)
      logs_embed.add_field(name="Attendee Discord", value=fetched_member.mention, inline=True)
      logs_embed.add_field(name="Attendee Roblox", value=username, inline=True)
      logs_embed.add_field(name="Command", value=command.name, inline=True)
      logs_embed.add_field(name="Division", value=division.name, inline=True)
      logs_embed.add_field(name="Main Rank", value=main_rank, inline=True)
      logs_embed.add_field(name="Division Rank", value=division_rank, inline=True)
      logs_embed.add_field(name="Company", value=company, inline=True)
      logs_embed.add_field(
          name="Submitted At",
          value=f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>",
          inline=False,
      )
      await logs_channel.send(embed=logs_embed)

  await interaction.followup.send(
      f"Your tryout request log with full security evaluation for {fetched_member.mention} has been successfully published to {dest_channel.mention} for review!",
      ephemeral=True,
  )


# Direct Group Rank Update Command (Restricted to Accepters/Admins)
@bot.tree.command(
    name="changerank",
    description="Directly change a member's rank in a Roblox group/division.",
)
@app_commands.choices(
    command=[
        app_commands.Choice(name="Military Police Corps", value="Military Police Corps"),
    ],
    division=[
        app_commands.Choice(name="Military Police School", value="Military Police School"),
        app_commands.Choice(name="Judge Advocate General Corps", value="Judge Advocate General Corps"),
        app_commands.Choice(name="503rd Battalion", value="503rd Battalion"),
        app_commands.Choice(name="14th Battalion", value="14th Battalion"),
        app_commands.Choice(name="Criminal Investigation Division", value="Criminal Investigation Division"),
    ],
)
@app_commands.autocomplete(
    main_rank=main_rank_autocomplete,
    division_rank=division_rank_autocomplete,
)
async def changerank(
    interaction: discord.Interaction,
    username: str,
    command: app_commands.Choice[str],
    division: app_commands.Choice[str],
    main_rank: str,
    division_rank: str,
):
  if not check_accepter_permission(interaction):
    await interaction.response.send_message(
        "❌ You do not have permission to change group ranks.", ephemeral=True
    )
    return

  await interaction.response.defer(ephemeral=True)

  user_search_url = f"https://users.roblox.com/v1/users/search?keyword={username}"
  user_resp = requests.get(user_search_url)

  if user_resp.status_code != 200 or not user_resp.json().get("data"):
    await interaction.followup.send(
        f"Failed to find Roblox user `{username}` via search API.",
        ephemeral=True,
    )
    return

  user_data = user_resp.json()["data"][0]
  roblox_user_id = user_data["id"]

  command_info = COMMAND_IDS.get(command.name)
  if not command_info:
    await interaction.followup.send(
        f"Invalid command mapping for `{command.name}`.", ephemeral=True
    )
    return

  main_group_id = command_info["main_id"]
  division_id = command_info["divisions"].get(division.name)

  # 1. Update Main Group Rank
  main_role_id = await get_target_role_id(main_group_id, main_rank)
  if not main_role_id:
    await interaction.followup.send(
        f"⚠️ Could not find exact Roblox role ID for Main Group rank `{main_rank}`.",
        ephemeral=True,
    )
    return

  success, msg = await apply_group_rank(main_group_id, roblox_user_id, main_role_id)
  if not success:
    await interaction.followup.send(
        f"Failed to update Main Group rank: `{msg}`", ephemeral=True
    )
    return

  # 2. Update Division Group Rank (if selected)
  if division_id and division_rank and division_rank != "None":
    div_role_id = await get_target_role_id(division_id, division_rank)
    if div_role_id:
      div_success, div_msg = await apply_group_rank(division_id, roblox_user_id, div_role_id)
      if not div_success:
        await interaction.followup.send(
            f"⚠️ Main group rank updated, but failed to update Division rank: `{div_msg}`",
            ephemeral=True,
        )
        return

  await interaction.followup.send(
      f"✅ Successfully updated **{username}'s** ranks in **{command.name}** "
      f"(Main Rank: {main_rank} | Division: {division.name} - {division_rank})!",
      ephemeral=False,
  )


@bot.event
async def on_ready():
  await bot.tree.sync()
  print(f"Logged in as {bot.user} - Fully updated to accept Discord ID string inputs for background checks!")


bot.run(os.getenv("DISCORD_BOT_TOKEN"))