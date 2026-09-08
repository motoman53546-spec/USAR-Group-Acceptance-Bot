import os
import discord
from discord.ext import commands
import requests

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

ROBLOX_API_KEY = os.getenv("ROBLOX_API_KEY")

# Dictionary mapping friendly names to your Roblox Group IDs
GROUP_IDS = {
    "MPC": "33846212",
    "ASOC": "16997678",
    "AAC": "33333333",
    "TRADOC": "44444444",
    "FORSCOM": "55555555",
}


class GroupQueueView(discord.ui.View):

  def __init__(self, username: str, join_request_path: str, group_name: str):
    super().__init__(timeout=180)
    self.username = username
    self.join_request_path = join_request_path
    self.group_name = group_name

  @discord.ui.button(
      label="Accept", style=discord.ButtonStyle.green, custom_id="accept_multi"
  )
  async def accept_user(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not interaction.user.guild_permissions.manage_roles:
      await interaction.response.send_message(
          "You do not have permission to manage acceptances.", ephemeral=True
      )
      return

    # Defer immediately to prevent interaction token timeouts
    await interaction.response.defer()

    # Roblox Open Cloud v2 Accept Endpoint
    url = f"https://apis.roblox.com/cloud/v2/{self.join_request_path}:accept"
    headers = {
        "x-api-key": ROBLOX_API_KEY,
        "Content-Type": "application/json",
    }

    response = requests.post(url, headers=headers)

    for child in self.children:
      child.disabled = True

    try:
      await interaction.edit_original_response(view=self)
    except Exception:
      pass

    if response.status_code == 200:
      await interaction.followup.send(
          f"Successfully accepted **{self.username}** into **{self.group_name}**"
          f" via {interaction.user.mention}!",
          ephemeral=False,
      )
    else:
      await interaction.followup.send(
          f"Failed to accept user. Error: `{response.text}`", ephemeral=True
      )

  @discord.ui.button(
      label="Deny", style=discord.ButtonStyle.red, custom_id="deny_multi"
  )
  async def deny_user(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not interaction.user.guild_permissions.manage_roles:
      await interaction.response.send_message(
          "You do not have permission to manage acceptances.", ephemeral=True
      )
      return

    await interaction.response.defer()

    url = f"https://apis.roblox.com/cloud/v2/{self.join_request_path}:decline"
    headers = {
        "x-api-key": ROBLOX_API_KEY,
        "Content-Type": "application/json",
    }

    response = requests.post(url, headers=headers)

    for child in self.children:
      child.disabled = True

    try:
      await interaction.edit_original_response(view=self)
    except Exception:
      pass

    await interaction.followup.send(
        f"Declined join request for **{self.username}** in"
        f" **{self.group_name}**.",
        ephemeral=False,
    )


@bot.tree.command(
    name="requests",
    description="View pending join requests for a specific military group.",
)
@discord.app_commands.choices(
    branch=[
        discord.app_commands.Choice(name="ASOC", value="ASOC"),
        discord.app_commands.Choice(name="MPC", value="MPC"),
        discord.app_commands.Choice(name="AAC", value="AAC"),
        discord.app_commands.Choice(name="TRADOC", value="TRADOC"),
        discord.app_commands.Choice(name="FORSCOM", value="FORSCOM"),
    ]
)
async def requests_cmd(
    interaction: discord.Interaction, branch: discord.app_commands.Choice[str]
):
  if not interaction.user.guild_permissions.manage_roles:
    await interaction.response.send_message(
        "You do not have permission to view group requests.", ephemeral=True
    )
    return

  await interaction.response.defer(ephemeral=True)

  group_id = GROUP_IDS.get(branch.value)
  url = f"https://apis.roblox.com/cloud/v2/groups/{group_id}/join-requests"
  headers = {"x-api-key": ROBLOX_API_KEY}

  response = requests.get(url, headers=headers)

  if response.status_code != 200:
    await interaction.followup.send(
        f"Failed to fetch requests for {branch.name}. Status Code:"
        f" `{response.status_code}`",
        ephemeral=True,
    )
    return

  data = response.json().get("groupJoinRequests", [])

  if not data:
    await interaction.followup.send(
        f"There are no pending join requests for **{branch.name}**.",
        ephemeral=True,
    )
    return

  # Grab the first request in the queue
  first_req = data[0]
  user_path = first_req.get("user")
  req_path = first_req.get("path")

  embed = discord.Embed(
      title=f"Pending Join Request — {branch.name}",
      description=(
          f"**User ID Path:** `{user_path}`\n**Request Path:** `{req_path}`"
      ),
      color=discord.Color.dark_blue(),
  )

  view = GroupQueueView(
      username=user_path, join_request_path=req_path, group_name=branch.name
  )
  await interaction.followup.send(embed=embed, view=view, ephemeral=True)


@bot.event
async def on_ready():
  await bot.tree.sync()
  print(f"Logged in as {bot.user} - Multi-group bot online!")


bot.run(os.getenv("DISCORD_BOT_TOKEN"))