import discord
import asyncio
import time
import json
import os

from dotenv import load_dotenv
from discord.ext import commands

# -----------------------------
# Load Environment Variables
# -----------------------------
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

# -----------------------------
# Bot Class
# -----------------------------
class Client(commands.Bot):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Active timers
        self.user_timers = {}

        # Files
        self.usage_file = "usage_stats.json"
        self.config_file = "bot_config.json"

        # Usage stats
        self.usage_stats = self.load_usage_stats()

        # Embed tracking
        self.embed_message_id = None
        self.embed_channel_id = None

        self.load_config()

        # Crops
        self.crops = {
            "event veggies": (900, "🥬 Time to harvest Event Veggies!"),
            "tomato": (900, "🍅 Time to harvest Tomato!"),
            "potato": (3600, "🥔 Time to harvest Potato!"),
            "wheat": (14400, "🌾 Time to harvest Wheat!"),
            "lettuce": (28800, "🥬 Time to harvest Lettuce!"),
            "pineapple": (1800, "🍍 Time to harvest Pineapple!"),
            "carrot": (7200, "🥕 Time to harvest Carrot!"),
            "strawberry": (21600, "🍓 Time to harvest Strawberry!"),
            "corn": (43200, "🌽 Time to harvest Corn!"),
            "grape": (36000, "🍇 Time to harvest Grape!"),
            "eggplant": (25200, "🍆 Time to harvest Eggplant!"),
            "tea tree": (2760, "🌲 Time to drink Matcha!"),
            "cacao tree": (18000, "🍫 Time to eat Chocolate!"),
            "avocado": (50400, "🥑 Time to harvest Avocado!"),
            "truffle": (780, "🍄 Time to harvest Truffle!"),
            "ordering machine": (259200, "👚 Time to use the Ordering Machine!")
        }

    # -----------------------------
    # Startup
    # -----------------------------
    async def on_ready(self):

        print(f"Logged in as {self.user}")

        # Persistent buttons
        self.add_view(CropView(self))

        guild = discord.Object(id=GUILD_ID)
        await self.tree.sync(guild=guild)

        print("Slash commands synced")

    # -----------------------------
    # Usage Tracking
    # -----------------------------
    def load_usage_stats(self):

        if os.path.exists(self.usage_file):

            with open(self.usage_file, "r") as f:
                return json.load(f)

        return {}

    def save_usage_stats(self):

        with open(self.usage_file, "w") as f:
            json.dump(self.usage_stats, f, indent=4)

    def log_crop_usage(self, user, crop):

        user_id = str(user.id)

        if user_id not in self.usage_stats:

            self.usage_stats[user_id] = {
                "name": user.name,
                "total_calls": 0,
                "crops": {}
            }

        self.usage_stats[user_id]["name"] = user.name
        self.usage_stats[user_id]["total_calls"] += 1

        crops = self.usage_stats[user_id]["crops"]
        crops[crop] = crops.get(crop, 0) + 1

        self.save_usage_stats()

    # -----------------------------
    # Config Persistence
    # -----------------------------
    def load_config(self):

        if os.path.exists(self.config_file):

            with open(self.config_file, "r") as f:

                data = json.load(f)

                self.embed_message_id = data.get("embed_message_id")
                self.embed_channel_id = data.get("embed_channel_id")

    def save_config(self):

        with open(self.config_file, "w") as f:

            json.dump({
                "embed_message_id": self.embed_message_id,
                "embed_channel_id": self.embed_channel_id
            }, f, indent=4)

    # -----------------------------
    # Timer Finish
    # -----------------------------
    async def delayed_response(
        self,
        user,
        delay,
        content,
        crop,
        end_time
    ):

        try:

            await asyncio.sleep(delay)

            await user.send(content)

            entries = self.user_timers.get(user.id, [])

            updated = [
                (t, c, e)
                for (t, c, e) in entries
                if not (c == crop and e == end_time)
            ]

            if updated:
                self.user_timers[user.id] = updated

            else:
                if user.id in self.user_timers:
                    del self.user_timers[user.id]

        except asyncio.CancelledError:
            pass

        except discord.Forbidden:
            pass


# -----------------------------
# Utility
# -----------------------------
def format_time(seconds: int) -> str:

    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)

    if h:
        return f"{h}h {m}m"

    if m:
        return f"{m}m {s}s"

    return f"{s}s"


# -----------------------------
# Crop Button
# -----------------------------
class CropButton(discord.ui.Button):

    def __init__(self, crop_name: str, row: int):

        super().__init__(
            label=crop_name.title(),
            style=discord.ButtonStyle.primary,
            row=row,
            custom_id=f"crop_{crop_name}"
        )

        self.crop_name = crop_name

    async def callback(self, interaction: discord.Interaction):

        bot: Client = interaction.client

        delay, response = bot.crops[self.crop_name]

        await interaction.response.send_message(
            f"{self.crop_name.title()} timer started.",
            ephemeral=True
        )

        end_time = time.time() + delay

        task = asyncio.create_task(
            bot.delayed_response(
                interaction.user,
                delay,
                response,
                self.crop_name,
                end_time
            )
        )

        bot.user_timers.setdefault(interaction.user.id, []).append(
            (task, self.crop_name, end_time)
        )

        # Usage logging
        bot.log_crop_usage(interaction.user, self.crop_name)


# -----------------------------
# Update Button
# -----------------------------
class UpdateButton(discord.ui.Button):

    def __init__(self, row: int):

        super().__init__(
            label="UPDATE",
            style=discord.ButtonStyle.success,
            emoji="🔁",
            row=row,
            custom_id="update_button"
        )

    async def callback(self, interaction: discord.Interaction):

        bot: Client = interaction.client

        now = time.time()

        entries = bot.user_timers.get(interaction.user.id, [])

        if not entries:

            await interaction.response.send_message(
                "You have no active timers.",
                ephemeral=True
            )

            return

        crops = {}

        for task, crop, end_time in entries:

            remaining = max(0, int(end_time - now))

            crops.setdefault(crop, []).append(remaining)

        lines = [
            f"• {crop.title()} × {len(times)} — next ready in {format_time(min(times))}"
            for crop, times in crops.items()
        ]

        await interaction.response.send_message(
            "**Your active timers:**\n" + "\n".join(lines),
            ephemeral=True
        )


# -----------------------------
# Stop Button
# -----------------------------
class StopButton(discord.ui.Button):

    def __init__(self, row: int):

        super().__init__(
            label="STOP",
            style=discord.ButtonStyle.danger,
            emoji="🛑",
            row=row,
            custom_id="stop_button"
        )

    async def callback(self, interaction: discord.Interaction):

        bot: Client = interaction.client

        tasks = bot.user_timers.get(interaction.user.id, [])

        if not tasks:

            await interaction.response.send_message(
                "You have no active timers.",
                ephemeral=True
            )

            return

        for task, crop, end_time in tasks:
            task.cancel()

        bot.user_timers[interaction.user.id] = []

        await interaction.response.send_message(
            f"Stopped {len(tasks)} timer(s).",
            ephemeral=True
        )


# -----------------------------
# View
# -----------------------------
class CropView(discord.ui.View):

    def __init__(self, bot: Client):

        super().__init__(timeout=None)

        row = 0
        count = 0

        for crop in bot.crops.keys():

            self.add_item(CropButton(crop, row))

            count += 1

            if count % 5 == 0:
                row += 1

        self.add_item(UpdateButton(row=4))
        self.add_item(StopButton(row=4))


# -----------------------------
# Bot Setup
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True

client = Client(
    command_prefix="!",
    intents=intents
)

GUILD = discord.Object(id=GUILD_ID)


# -----------------------------
# Embed Command
# -----------------------------
@client.tree.command(
    name="embed",
    description="Posts the ReadMe",
    guild=GUILD
)
async def embed(interaction: discord.Interaction):

    bot: Client = interaction.client

    await interaction.response.defer(ephemeral=True)

    embed = discord.Embed(
        title="Crops Countdown [Bot]",
        color=discord.Colour.brand_green()
    )

    embed.add_field(
        name="Crops Countdown",
        value=(
            "Track crop growth times and get notified when they are ready.\n"
        ),
        inline=False
    )

    embed.add_field(
        name="How To Use",
        value=(
            "Click crop buttons below to start timers.\n"
            "At harvest time you will receive a **Direct Message**.\n"
            "Press **Update** to receive information regarding current timers.\n"
            "**Stop** will delete all current timers."
        ),
        inline=False
    )

    embed.add_field(
        name="\u200b",
        value=(
            "🥬 Event Veggies – 15 mins\n"
            "🍅 Tomato – 15 mins\n"
            "🥔 Potato – 60 mins\n"
            "🌾 Wheat – 4 hours\n"
            "🥬 Lettuce – 8 hours\n"
            "🍍 Pineapple – 30 mins\n"
            "🥕 Carrot – 2 hours\n"
            "🍓 Strawberry – 6 hours\n"
            "🌽 Corn – 12 hours\n"
            "🍇 Grape – 10 hours\n"
            "🍆 Eggplant – 7 hours\n"
            "🌲 Tea Tree – 45 mins\n"
            "🍫 Cacao Tree – 5 hours\n"
            "🥑 Avocado – 14 hours\n"
            "🍄 Truffle – 13 mins\n"
            "👚 Ordering Machine – 3 days\n"
        ),
        inline=False
    )

    embed.set_footer(
        text="🔔 Controls are only visible to you."
    )

    view = CropView(bot)

    # Delete old embed if possible
    if bot.embed_message_id and bot.embed_channel_id:

        try:

            channel = await client.fetch_channel(
                bot.embed_channel_id
            )

            old = await channel.fetch_message(
                bot.embed_message_id
            )

            await old.delete()

        except Exception:
            pass

    # Post new embed
    msg = await interaction.channel.send(
        embed=embed,
        view=view
    )

    # Save embed info
    bot.embed_message_id = msg.id
    bot.embed_channel_id = msg.channel.id

    bot.save_config()

    await interaction.followup.send(
        "Embed reposted at bottom.",
        ephemeral=True
    )


# -----------------------------
# Run Bot
# -----------------------------
client.run(TOKEN)
