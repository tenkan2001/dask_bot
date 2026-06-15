import discord, asyncio, json, datetime, os
from google_auth_oauthlib.flow import InstalledAppFlow
from cogs.weather import OpenWeatherMapAPIClient
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from discord.ext import commands
from dotenv import load_dotenv
from cogs.database import UserLocation, TaskCompleted
from asyncio import to_thread
from discord import app_commands
from discord.ui import View, Select

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WEATHER_TOKEN = os.getenv("WEATHER_TOKEN")

CREDENTIALS_FILE = './.secret/credentials.json'
TOKEN_FILE = './.secret/saved_token.json'
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly', 'https://www.googleapis.com/auth/tasks.readonly', 'https://www.googleapis.com/auth/tasks'] #les scopes sont des permissions securisée de google

weather_client = OpenWeatherMapAPIClient(WEATHER_TOKEN, "MyDiscordWeatherBot")
intents = discord.Intents(messages=True, guilds=True)
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
user_location_db = UserLocation()
task_completed_db = TaskCompleted()
TZ = datetime.datetime.now().astimezone().tzinfo

#ici avec le token google et les permissions utilisés, on appel le service agenda de google
def build_calendar_service():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    return build('calendar', 'v3', credentials=creds)

#idem mais avec google tâches
def build_tasks_service():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    service = build('tasks', 'v1', credentials=creds)
    return service

#ici l'horaire récupéré par l'API est formatter pour qu'il soit plus lisible
def parse_rfc3339_to_local_date(ts):
    if not ts:
        return None
    try:
        s = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
        if "T" in ts:
            dt = datetime.datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone(TZ).date()
        return datetime.date.fromisoformat(s)
    except Exception:
        return None

#Se connecter au compte google depuis lequel on voudrait les infos
async def authenticate():
    if os.path.exists(TOKEN_FILE):
        print("Token file exists; skipping interactive authentication.")
        return
    
    print("No token found: running interactive OAuth flow(will open browser).")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    credentials = flow.run_local_server(port=0)

    with open(TOKEN_FILE, 'w') as f:  #sauvegarde les credentiels du compte utilisé pour pas se connecter à chaque fois
        f.write(credentials.to_json())
    print(f"Saved credentials to {TOKEN_FILE} for instant access")

#Classe qui marque les tâches comme "fait"
class TaskSelect(Select):
    def __init__(self, options):
        super().__init__(placeholder="Choose a task to complete...",
        min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        payload = json.loads(self.values[0])
        tasklist_id = payload["tasklist_id"]
        task_id = payload["task_id"]

        await interaction.response.defer(thinking=True)
        try:
            service = build_tasks_service()
            task = await asyncio.to_thread(lambda:
                service.tasks().get(tasklist=tasklist_id, task=task_id).execute())
            if not task:
                await interaction.followup.send("Task not found.", ephemeral=True)
                return

            if task.get("status") == "completed":
                await interaction.followup.send("Task already completed.", ephemeral=True)
                return

            now = datetime.datetime.now(TZ).isoformat()
            body = dict(task)
            body["status"] = "completed"
            body["completed"] = now

            updated = await asyncio.to_thread(lambda: service.tasks().update(tasklist=tasklist_id, task=task_id, body=body).execute())

            if updated.get("status") == "completed":
                await interaction.followup.send(f"User {interaction.user.display_name} marked task '{updated.get('title')}' as completed.", ephemeral=True)
                print(f"User {interaction.user.display_name} just completed task {updated.get('title')}")
                username = interaction.user.display_name
                user_id = interaction.user.id
                task = updated.get('title')
                time = now
                task_completed_db.set_info(user_id, username, task, time)
        
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

#ajout de classe TaskSelect à la partie ui
class TasksView(View):
    def __init__(self, options, timeout=120):
        super().__init__(timeout=timeout)
        self.add_item(TaskSelect(options))


#commande qui affiche les tâches à faire sauvegardé sur google tasks
@bot.tree.command(name="daily_tasks", description="Check today's saved tasks and complete them")
async def today(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    print(f'Recieved daily_tasks command by {interaction.user.display_name}')
    try:
        service = build_tasks_service()
        tl_res = await asyncio.to_thread(lambda: service.tasklists().list(maxResults=100).execute())
        lists = tl_res.get("items", []) or []

        today = datetime.datetime.now(tz=TZ).date()

        embed = discord.Embed(
            title="Today's tasks",
            color=0x2ecc71,
            timestamp=datetime.datetime.now(tz=TZ)
        )

        options = []
        total = 0
        
        #Boucle for qui passe par chaque liste des tâches
        for tl in lists:
            tl_id = tl.get("id")
            tl_title = tl.get("title") or "<untitled>"

            tasks_res = await asyncio.to_thread(lambda: service.tasks().list(
                tasklist=tl_id, showCompleted=True, showHidden=True, maxResults=250).execute() or {})
            items = tasks_res.get("items", []) or []

            
            #Boucle for qui passe par chaque tâche dans le liste de tâche
            for t in items:    
                if not isinstance(t, dict):        
                    continue
                
                due_date = parse_rfc3339_to_local_date(t.get("due"))
                completed_date = parse_rfc3339_to_local_date(t.get("completed"))

                if due_date != today and completed_date != today:
                   continue

                print(f"API RESPONSE:   {t}")

                total += 1
                status = "✅" if t.get("status") == "completed" else "🔲"
                t_id = t.get("id")
                title = t.get("title") or "(no title)"                

                embed.add_field(name=f"{tl_title} - {status} {title}", value=f"ID: {t_id}", inline=False)

                value = json.dumps({"tasklist_id": tl_id, "task_id": t_id})
                options.append(discord.SelectOption(label=(title[:90] or "(no title)"), description=tl_title[:50], value=value))
            

        if total == 0:
            await interaction.followup.send("No tasks due today.")
            return

        options = options[:25]
        view = TasksView(options, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        await interaction.followup.send(f"An error occured:{e}")

#commande qui affiche les évenements sauvegardé sur google agenda
@bot.tree.command(name='weekly_events', description="Check this weeks saved events")
async def events(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    
    print(f'Recieved weekly_events command by {interaction.user.display_name}')
    try:
        service = build_calendar_service()
    except FileNotFoundError:
        await interaction.followup.send("Calendar credentials not found.")
        return
    except Exception as e:
        await interaction.followup.send(f"Failed to build service: {e}")
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    current_weekday = now.weekday()

    start_of_week = now - datetime.timedelta(days=current_weekday)
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)

    end_of_week = start_of_week + datetime.timedelta(days=6)
    end_of_week= end_of_week.replace(hour=23, minute=59, second=59, microsecond=999999)

    print(f"Start of week: {start_of_week.isoformat()}, End of week: {end_of_week.isoformat()}")

    try:
        events_result = service.events().list(
            calendarId='primary', 
            timeMin=start_of_week.isoformat(),
            timeMax=end_of_week.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        print(f"API RESPONSE:   {events_result}")
        events = events_result.get('items',[])  
       

        
        if not events:
            await interaction.followup.send("No events this week!")
            return

        else:
            embed = discord.Embed(
                 title="📅 This week's events",
                 color=discord.Color.blue(),
                 timestamp=datetime.datetime.now(tz=TZ)
            )
            
            for event in events:

                event_description = event.get('description', '')

                if 'tasks.google.com' in event_description:
                    continue 

                event_time_str = event['start'].get('dateTime', event['start'].get('date'))
                if 'Z' in event_time_str:
                    event_time = datetime.datetime.fromisoformat(event_time_str.replace('Z', '+00:00'))
                else:
                    event_time = datetime.datetime.fromisoformat(event_time_str)

                event_time_local = event_time.strftime("%A, %B %d, %Y, %H:%M")

                task = f"**{event['summary']}**\n⏰ {event_time_local}\n Description: {event_description}"
                embed.add_field(name="\u200b", value=task, inline=False)

            await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f'An error occurred: {e}')


#Commande qui enregistre le localisation du user
@bot.command(name="set_location")
async def set_location(ctx, *, location: str):
    user_id = ctx.author.id
    username = ctx.author.display_name
    user_location_db.set_user_location(username, user_id, location)
    await ctx.send(f"Location set to: {location}")
    print(f"{username} just set location to {location}")


#Commande qui affiche la météo du jour 
@bot.tree.command(name="weather", description="Check the weather!")
async def current_weather(interaction: discord.Interaction, location: str = None):
    user_id = interaction.user.id
    
    if location is None:
        location = user_location_db.get_user_location(user_id)
        if not location:
            await interaction.response.send_message("Please provide a location or set one using '!set_location <location>'.\n(Your location will be stored in a database for ease of access)")
            return

    print(f"Received weather command from {interaction.user.display_name}")  # Log intéraction

    current_weather = weather_client.get_current_weather(location)

    print(f"API RESPONSE    {current_weather}")

    # Vérifier que current_weather est un dictionnaire et contient les clés nécessaires
    if isinstance(current_weather, dict) and 'main' in current_weather and 'weather' in current_weather:    
        weather_condition = current_weather['weather'][0]['main'] 
        temp = current_weather['main']['temp']   
        icon = current_weather['weather'][0]['icon']

        embed = discord.Embed(
            title=f"Current weather in {location}",
            description=f"Temperature: {temp}°C\nWeather condition: {weather_condition}",
            color=discord.Color.yellow(),
            timestamp=datetime.datetime.now(tz=TZ)
        )
        embed.set_thumbnail(url=f"https://openweathermap.org/img/wn/{icon}.png")

        await interaction.response.send_message(embed=embed)

    else:
        await interaction.response.send_message("Could not retrieve weather data. Please check the location or try again. ")

#Cette partie est le "main" qui écoute les commandes et le lance quand ils sont appelés
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await authenticate()
    await bot.tree.sync()
#Liste commandes enregistré
    commands = await bot.tree.fetch_commands()
    print("Registered Commands:")
    for command in commands:
        print(f"- {command.name}")
    print("- !set_location")

    channel = bot.get_channel("add id here without the quotation")
    if channel:
        embed = discord.Embed(
            description="Bot is now online and ready to serve! Type / to check available commands"
        )
        await channel.send(embed=embed)

    print("your bot is online and ready to serve !")


bot.run(DISCORD_TOKEN)
