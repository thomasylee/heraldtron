import discord, asyncio, typing, random, os, html
from discord.ext import commands
from .. import converters, embeds, services, responses, utils

class MiscStuff(utils.MeldedCog, name = "Miscellaneous", category = "Other", limit = True):
	COUNTDOWN_LIMIT = 3
	ACTIVITIES = {
		-1: "",
		0: "Playing",
		1: "Streaming",
		2: "Listening to",
		3: "Watching",
		4: "Activity:",
		5: "Competing in" 
	}
	
	def __init__(self, bot):
		self.bot = bot
		
	@commands.command(help = "Retrieves a random piece of advice.\nUses adviceslip.com", aliases = ("ad",))
	@utils.trigger_typing
	async def advice(self, ctx):			
		result = await utils.get_json(self.bot.session,f"https://api.adviceslip.com/advice",content_type="text/html")
		
		embed = embeds.GENERIC.create(result["slip"]["advice"], "", heading = "Random advice")		
		embed.set_footer(text=f"Retrieved using adviceslip.com")
		await ctx.send(embed = embed)
	
	@commands.command(
		help = "Generates a continuously updated countdown post.", 
		aliases = ("time", "cd")
	)
	async def countdown(self, ctx, *, elapsed : converters.Date):		
		amount = await self.bot.dbc.execute_fetchone(
			"SELECT COUNT(*) FROM countdowns WHERE user_id == ?;", (ctx.author.id,)
		)
		
		if amount[0] > self.COUNTDOWN_LIMIT:
			raise utils.CustomCommandError(
				"Too many active countdowns",
				f"A user can only have {self.COUNTDOWN_LIMIT} countdowns active at once."
			)
		
		embed, delta = embeds.countdown(elapsed)
		
		if delta.total_seconds() < 0:
			raise utils.CustomCommandError(
				"Date has already occured",
				"The date that you entered is in the past."
			)
		
		desc = (await responses.respond_or_react(
			ctx,
			f"Your countdown will expire at **{utils.stddatetime(elapsed)}**. Now,"
			" give it a name by responding below, or react with :x: to cancel."
		)).content
		
		embed.description = desc	
		message = await ctx.send(embed = embed)
		
		await self.bot.dbc.execute(
			"INSERT INTO countdowns (timestamp, user_id, channel_id, message_id, name) VALUES (?, ?, ?, ?, ?);",
			(elapsed.timestamp(), ctx.author.id, ctx.channel.id, message.id, desc)
		)
		await self.bot.dbc.commit()
		
	@commands.command(
		help = "Generates a competition distribution.\n If no number is specified, asks for a list of names.", 
		aliases = ("dt", "dist")
	)
	async def distribute(self, ctx, size : converters.Range(3, 50) = None):
		if not size:
			message = await responses.respond_or_react(
				ctx,
				"Enter a list of contestants separated by line breaks (\u21E7\u23CE on desktop)"
				", or react with :x: to cancel.",
				timeout = reponses.LONG_TIMEOUT
			)
			names = dict(enumerate(message.content.split("\n"), start = 1))
			size = converters.Range(3, 50).convert(len(names))
		else: names = None
					
		def distribution(keysize):
			vals = list(range(1, keysize))
			candidates = {i: None for i in range(1, keysize)}
			
			for c in candidates:
				same = c in vals
				
				if len(vals) == 1 and same: #try again, no valid option			
					candidates = distribution(keysize)
					break 	
				elif same: vals.remove(c)
				
				candidates[c] = vals.pop(random.randrange(0, len(vals)))
				if same: vals.append(c)
				
			return candidates
		
		dist = distribution(size + 1)
		display = lambda e: f"**{e}**: {names[e]}" if names else f"**{e}**"
		output = "".join(f"{display(k)} \U0001F86A {display(v)}\n" for k, v in dist.items())
		
		await ctx.send(output)
		
	@commands.command(help = "Conducts a search using Google Images.", aliases = ("img", "gi"))
	@utils.trigger_typing
	async def imgsearch(self, ctx, *, query):
		await services.gis(ctx, "" + query)

	@commands.command(
		help = "Chooses a random number.\n"
		" By default, this is out of 6, but another value can be specified.",
		aliases = ("dice", "d")
	)
	async def roll(self, ctx, ceiling : converters.Range(2, 9999) = 6):		
		message = await ctx.send(":game_die: | Rolling the dice...")
		result = random.randrange(1, ceiling + 1)
		await asyncio.sleep(2)
		await message.edit(content=f":game_die: | The dice landed on... **{result}**!")
		
	@commands.command(help = "Sends a post as the bot user. Handy for jokes and such.", aliases = ("st",), hidden = True)
	@commands.is_owner()	
	async def sendtext(ctx, channel : typing.Optional[discord.TextChannel] = None, *, message_content):
		channel = channel or ctx.channel
		await channel.send(message_content)
		
	@commands.command(
		help = "Completes a passage of text using machine learning.\n"
			   " This uses DeepAI's online model to compute the result.",
		aliases=("aitext", "tg")
	)
	@utils.trigger_typing
	async def textgen(self, ctx, *, text : str):
		url = "https://api.deepai.org/api/text-generator"
		data = {"text": text.strip()}
		headers = {"api-key": ctx.bot.conf["DEEP_AI"].strip()}
			
		async with ctx.bot.session.post(url, data = data, headers = headers) as source:
			if not source.ok:
				raise utils.CustomCommandError(
					"Invalid HTTP request",
					f"Please try again. If problems persist, contact the bot's maintainer."
				)
			
			result_json = await source.json()
		
		result = result_json["output"]	
		newtext = result[result.index(text) + len(text):]
		
		await ctx.send(f":abcd: | **Text generated!**\n\n*{text}*{newtext}")
		
	@commands.group(
		invoke_without_command = True,
		help = "Asks a trivia question that users can react to.\n"
			   "Optionally, a numeric category can be specified."
			   "\nCourtesy of the Open Trivia Database.\n\u0020\n",
		aliases = ("q","tr")
	)
	@utils.trigger_typing
	async def trivia(self, ctx, category : typing.Optional[int] = -1):
		catstring = "" if category == -1 else f"&category={category}"
		json = f"https://opentdb.com/api.php?amount=1{catstring}"
		result = await utils.get_json(self.bot.session, json)
		
		if result["response_code"] == 1:
			raise utils.CustomCommandError(
				"Invalid category code",
				f"Consult `!trivia categories` to see the available codes."
			)
			
		result = result["results"][0]
		info = f"**{result['category']}** | {result['difficulty'].capitalize()}\n\n"
		embed = embeds.GENERIC.create(html.unescape(result["question"]), info, heading = "Trivia")
		
		if result["type"] == "boolean":
			emojis = ("\U0001F438", "\U0001F430")
			correct = random.randrange(0,2)
		else:
			emojis = ("\U0001F431", "\U0001F436", "\U0001F434", "\U0001F43B")
			correct = random.randrange(0,4)
			
		answers = result["incorrect_answers"]
		answers.insert(correct,result["correct_answer"])
		
		for num, answer in enumerate(answers):
			embed.description += f"- {emojis[num]} {html.unescape(answer)}\n\n"
			
		embed.description += f"React to respond. The correct answer will appear in **one minute.**"
		
		embed.set_footer(text = f"Courtesy of the Open Trivia Database.")
		message = await ctx.send(embed = embed)
		await responses.multi_react(message, emojis)
		await asyncio.sleep(60)
		
		embed.description = f"{info}The correct answer is: {emojis[correct]}"\
		 					f" **{html.unescape(answers[correct])}**"
		updated = await message.channel.fetch_message(message.id)
		
		if updated is None: return #message deleted
		
		response_lines = ""

		for react in updated.reactions:
			if react.emoji not in emojis or react.count == 1: continue
			
			num = emojis.index(react.emoji)
			respondents = []
			emoji_str = str(react.emoji)
			
			async for user in react.users():
				if user == ctx.bot.user: continue
				respondents.append(user.mention)
				
			response_lines += f"\n- {emoji_str} {answers[num]}: "\
						   f"{', '.join(respondents)} (**{react.count - 1}**)\n\u200b"
						   
		if response_lines:
			embed.description += f"\n\n**Responses:**\n\u0020{response_lines}"
		
		await message.edit(embed = embed)
		
		if isinstance(ctx.channel, discord.abc.GuildChannel):
			await message.clear_reactions()
			
	@trivia.command(help = "Lists all categories.")
	async def categories(self, ctx):
		result = await utils.get_json(self.bot.session, f"https://opentdb.com/api_category.php") 
		embed = embeds.GENERIC.create(
			"Trivia categories", "To choose a category, specify its numeric ID.", heading = "Trivia"
		)
		
		for category in result["trivia_categories"]:
			embed.add_field(name = category["name"], value=category["id"], inline=True)	
			
		embed.set_footer(text = f"Courtesy of the Open Trivia Database.")
		await ctx.send(embed = embed)
		
	@commands.command(help = "Looks up a Discord user.", aliases = ("u",))
	@utils.trigger_typing
	async def user(self, ctx, *, user : converters.MemberOrUser = None):
		user = user or ctx.author
		
		if not isinstance(user, discord.Member) and ctx.guild:
			user = ctx.guild.get_member(user.id) or user
		
		embed = embeds.USER_INFO.create(f"{user.name}#{user.discriminator}", f"{user.mention}")
		if user.bot:
			embed.description += " | **Bot**"
			
		embed.set_thumbnail(url = user.avatar.with_size(512).url)
		embed.add_field(name = "Created", value = utils.stddate(user.created_at), inline = True)
		embed.description += "\n\u200b"
		
		if isinstance(user, discord.Member):
			embed.colour = user.colour if user.colour.value != 0 else embeds.DEFAULT
						
			for activity in user.activities:
				preface = activity.emoji or "" if hasattr(activity, "emoji") else f"**{self.ACTIVITIES[int(activity.type)]}**"
				embed.description += f"\n{preface} {activity.name}"
			
			embed.add_field(name = "Joined", value = utils.stddate(user.joined_at), inline = True)
			embed.add_field(name = "Status", value = f"Currently **{user.raw_status}**", inline = True)
			
			if isinstance(ctx.channel, discord.abc.GuildChannel):
				roles = (str(role.mention) for role in user.roles[1:])
				embed.add_field(name = "Roles", value = ", ".join(("@everyone ", *roles)), inline = False)
		
		await ctx.send(embed = embed)
	
		
def setup(bot):
	bot.add_cog(MiscStuff(bot))