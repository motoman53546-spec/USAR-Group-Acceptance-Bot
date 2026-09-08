import os
import discord
from discord import app_commands
from discord.ext import commands
import requests

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


class HighCommandReviewView(discord.ui.View):

  def __init__(
      self,
      username: str,
      group_name: str,
      division: str,
      company: str,
      notes: str,
      proof_url: str,
      instructor: discord.User,
  ):
    super().__init__(timeout=None)
    self.username = username
    self.group_name = group_name
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
    if not interaction.user.guild_permissions.manage_roles:
      await interaction.response.send_message(
          "Only High Command can approve tryout request logs.", ephemeral=True
      )
      return

    await interaction.response.defer()

    # Step 1: Find the Roblox user ID from the username provided
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

    # Step 2: Check or hit Roblox Open Cloud to post/verify join request queue
    # Note: Roblox Open Cloud v2 requires the user to already have an active join request
    # in the group to accept them via API. Let's list pending requests to find their specific path.
    requests_url = (
        f"https://apis.roblox.com/cloud/v2/groups/{group_id}/join-requests"
    )
    headers = {"x-api-key": ROBLOX_API_KEY}
    get_reqs = requests.get(requests_url, headers=headers)

    target_request_path = None
    if get_reqs.status_code == 200:
      for req in get_reqs.json().get("groupJoinRequests", []):
        # req['user'] looks like 'users/12345678'
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

    # Step 3: Accept via Open Cloud v2 endpoint
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
      await interaction.followup.send(
          f"Successfully approved and admitted **{self.username}** into"
          f" **{self.group_name}** ({self.division} / {self.company}) by High"
          f" Command {interaction.user.mention}!",
          ephemeral=False,
      )
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
    if not interaction.user.guild_permissions.manage_roles:
      await interaction.response.send_message(
          "Only High Command can manage requests.", ephemeral=True
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


@bot.tree.command(
    name="grouprequest",
    description="Submit a tryout completion log for High Command review.",
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
async def grouprequest(
    interaction: discord.Interaction,
    username: str,
    branch: app_commands.Choice[str],
    division: str,
    company: str,
    notes: str,
    proof: discord.Attachment,
):
  await interaction.response.defer(ephemeral=True)

  embed = discord.Embed(
      title="Tryout Proof / Group Acceptance Log",
      description="A new tryout result has been submitted for review.",
      color=discord.Color.dark_red(),
  )
  embed.add_field(name="Attendee Username", value=username, inline=True)
  embed.add_field(name="Group Branch", value=branch.name, inline=True)
  embed.add_field(name="Division", value=division, inline=True)
  embed.add_field(name="Company", value=company, inline=True)
  embed.add_field(name="Notes / Result", value=notes, inline=False)
  embed.add_field(name="Tested By", value=interaction.user.mention, inline=True)
  embed.set_image(url=proof.url)
  embed.set_footer(text="Waiting for High Command Approval...")

  view = HighCommandReviewView(
      username=username,
      group_name=branch.name,
      division=division,
      company=company,
      notes=notes,
      proof_url=proof.url,
      instructor=interaction.user,
  )

  # Send the log embed into the current channel (or designate a logging channel ID if preferred)
  await interaction.channel.send(embed=embed, view=view)
  await interaction.followup.send(
      "Your tryout request log has been successfully published for High Command"
      " review!",
      ephemeral=True,
  )


@bot.event
async def on_ready():
  await bot.tree.sync()
  print(f"Logged in as {bot.user} - Tryout Log Bot Online!")


bot.run(os.getenv("DISCORD_BOT_TOKEN"))