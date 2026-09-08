import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


class ApplicationReviewView(discord.ui.View):

  def __init__(self, applicant: discord.Member):
    super().__init__(timeout=None)
    self.applicant = applicant

  @discord.ui.button(
      label="Accept", style=discord.ButtonStyle.green, custom_id="accept_app"
  .encode("utf-8")
  )
  async def accept_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    # Check if user has command staff permissions
    if not interaction.user.guild_permissions.manage_roles:
      await interaction.response.send_message(
          "You do not have permission to accept applications.", ephemeral=True
      )
      return

    # Disable buttons after action
    for child in self.children:
      child.disabled = True
    await interaction.message.edit(view=self)

    try:
      # Optional: Add roles or notify user via DM here
      await self.applicant.send(
          "Your application has been **accepted**! Welcome to the group."
      )
    except discord.Forbidden:
      pass

    await interaction.response.send_message(
        f"Application accepted by {interaction.user.mention} for"
        f" {self.applicant.mention}.",
        ephemeral=False,
    )

  @discord.ui.button(
      label="Deny", style=discord.ButtonStyle.red, custom_id="deny_app"
  )
  async def deny_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not interaction.user.guild_permissions.manage_roles:
      await interaction.response.send_message(
          "You do not have permission to deny applications.", ephemeral=True
      )
      return

    for child in self.children:
      child.disabled = True
    await interaction.message.edit(view=self)

    try:
      await self.applicant.send(
          "Your application has been reviewed, but unfortunately it was"
          " **denied** at this time."
      )
    except discord.Forbidden:
      pass

    await interaction.response.send_message(
        f"Application denied by {interaction.user.mention} for"
        f" {self.applicant.mention}.",
        ephemeral=False,
    )


@bot.tree.command(
    name="apply", description="Submit your application for review."
)
async def apply(interaction: discord.Interaction):
  await interaction.response.send_message(
      "Your application has been submitted to command staff for review!",
      ephemeral=True,
  )

  # Find a designated staff channel or send to a specific channel ID
  # Replace with your actual staff review channel ID
  staff_channel_id = os.getenv("STAFF_CHANNEL_ID")
  if staff_channel_id:
    channel = bot.get_channel(int(staff_channel_id))
    if channel:
      embed = discord.Embed(
          title="New Sub-Division Application",
          description=f"Applicant: {interaction.user.mention} ({interaction.user.id})",
          color=discord.Color.blue(),
      )
      view = ApplicationReviewView(interaction.user)
      await channel.send(embed=embed, view=view)


@bot.event
async def on_ready():
  await bot.tree.sync()
  print(f"Logged in as {bot.user} - Ready to process applications!")


bot.run(os.getenv("DISCORD_BOT_TOKEN"))