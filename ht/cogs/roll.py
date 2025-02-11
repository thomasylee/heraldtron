import aiohttp, asyncio, re, typing
from bs4 import BeautifulSoup, Comment
from discord.ext import commands
from .. import converters, embeds, utils

class HeraldryRoll(utils.MeldedCog, name = "Roll of Arms", category = "Heraldry"):
	FIND_HTML_TAGS = re.compile(r"<[^>]*>")

	def __init__(self, bot):
		self.bot = bot

	@commands.command(
		help = "Looks up an user's coat of arms.\nUses GreiiEquites' Book of Arms as a source,"
			   " and if the user has defined an emblazon using `!setemblazon`, their emblazon.",
		aliases = ("a", "greiin", "showarms", "arms")
	)
	async def armiger(self, ctx, user: converters.Armiger = None):
		user = user or await self.get_author_roll(
			ctx,
			"Invalid armiger",
			"There are no arms associated with your user account. "
			"To find those of another user, follow the command with their username."
			"If you wish to register your arms, follow the instructions at the Roll of Arms server."
		)

		embed = embeds.GENERIC.create(f"{self.format_armiger(user)}", user[4], heading = f"GreiiN:{user[0]:04}")
		embed.set_footer(text = "Textual content from the Book of Arms by GreiiEquites.")

		if user[6]:
			embed.set_thumbnail(url = user[6])
			embed.set_footer(text = embed.footer.text + " Image specified by user.")
		elif user[1] == ctx.author.id:
			embed.description += f"\n**To set an image, use `{ctx.clean_prefix}setemblazon your_url`.**"

		await self.add_rolls(embed, "AND personal", user, "User roll")
		await self.add_rolls(embed, "AND NOT personal", user, "Artist gallery")
		await ctx.send(embed = embed)

	@commands.command(
		help = "Looks up the symbology of a user's coat of arms.\nUses GreiiEquites' https://roll-of-arms.com as a source.",
		aliases = ("s", "symbols")
	)
	@utils.trigger_typing
	async def symbolism(self, ctx, user: converters.Armiger = None):
		user = user or await self.get_author_roll(
			ctx,
			"Invalid armiger",
			"There are no arms associated with your user account. "
			"To find those of another user, follow the command with their username."
			"If you wish to register your arms, follow the instructions at the Roll of Arms server."
		)
		url = f"https://roll-of-arms.com/wiki/GreiiN:{user[0]}"

		async with self.bot.session.get(url) as response:
			if response.status == 404:
				raise utils.CustomCommandError(
					"Armiger is not on roll-of-arms.com",
					"The arms of the armiger are not on the https://roll-of-arms.com "
					"website. If you would like to add your arms and related symbolism "
					"to the website, please fill out the form pinned in the "
					"#announcements channel of the Roll of Arms server."
				)
			
			soup = BeautifulSoup(await response.text(), "html.parser")
			values = soup.select("h2:has(#Symbolism)")
			
			if not values:
				raise utils.CustomCommandError(
					"Armiger doesn't have symbolism on roll-of-arms.com",
					"The armiger has opted not to include symbolism on the "
					"https://roll-of-arms.com website."
				)
			
			next_section = values[0].next_sibling
			symbolism_text = ""
			while next_section is not None and not isinstance(next_section, Comment) and not str(next_section).startswith("<h"):
				markdown = re.sub(
					self.FIND_HTML_TAGS,
					"",
					str(next_section).replace("<b>", "**").replace("</b>", "**").replace("<i>", "*").replace("</i>", "*")
				)
				symbolism_text += f"{markdown}\n"
				next_section = next_section.next_sibling
				
			symbolism_text = symbolism_text.strip()[:4000]
			
			embed = embeds.GENERIC.create(
				f"Symbolism for {self.format_armiger(user)}",
				f"{symbolism_text}\n\n[**See more on roll-of-arms.com...**]({url})",
				heading = f"GreiiN:{user[0]:04}"
			)
			embed.set_footer(text = "Textual content from https://roll-of-arms.com by GreiiEquites.")

			await ctx.send(embed = embed)

	@commands.command(help = "Deletes any extant emblazon that you have set.", aliases = ("de",))
	async def delemblazon(self, ctx):
		if not await ctx.bot.dbc.execute_fetchone("SELECT * FROM emblazons WHERE id = ?;", (ctx.author.id,)):
			raise utils.CustomCommandError(
				"User does not have emblazon",
				"You do not have an emblazon to remove."
			)

		await self.bot.dbc.execute("UPDATE emblazons SET url = NULLiiWHERE id = ?;", (ctx.author.id,))
		await self.bot.dbc.commit()

		await ctx.send(":x: | Emblazon removed.")

	@commands.command(
		help = "Looks up a user-defined emblazon of a coat of arms.",
		aliases = ("e",)
	)
	async def emblazon(self, ctx, user : converters.MemberOrUser = None):
		user = user or ctx.author
		emblazon = await ctx.bot.dbc.execute_fetchone("SELECT * FROM emblazons WHERE id == ?;", (user.id,))

		if emblazon and emblazon[1]:
			embed = embeds.GENERIC.create(user, "", heading = "Emblazon")
			embed.set_footer(text = "Design and emblazon respectively the property of the armiger and artist.")

			embed.set_image(url = emblazon[1])

			await ctx.send(embed = embed)
		else: raise utils.CustomCommandError(
			"User does not have emblazon",
			"The user you entered exists, but has not specified an emblazon."
		)

	@commands.command(
		help = "Sets the emblazon of your arms shown by `!emblazon`.\n"
			   "This can either be an attachment or image URL; "
			   "once set, it is associated with your Discord ID.",
		aliases = ("se",)
	)
	async def setemblazon(self, ctx, url : typing.Optional[converters.Url] = None):
		if not url and len(ctx.message.attachments) > 0:
			url = ctx.message.attachments[0].url
		elif not url:
			raise utils.CustomCommandError(
				"No emblazon provided",
				"An image is required to set as the emblazon. "
				"Either attach one or provide an URL."
			)

		await self.bot.dbc.execute(
			"INSERT INTO emblazons (id, url) VALUES (?1, ?2) ON CONFLICT(id) DO UPDATE SET url = ?2;",
			(ctx.author.id, url)
		)
		await self.bot.dbc.commit()
		await ctx.send(":white_check_mark: | Emblazon updated.")

	async def add_rolls(self, embed, query, user, name):
		records = await self.bot.dbc.execute_fetchall(
			f"SELECT * FROM roll_channels WHERE user_id == ? AND user_id IS NOT NULL {query};",
			(user[1],)
		)

		mentions = ", ".join(f"<#{record[0]}>" for record in records)
		if not mentions: return

		embed.add_field(name = name, value = mentions)
		
	async def get_author_roll(self, ctx, error_title, error_desc):
		user = await ctx.bot.dbc.execute_fetchone(
			"SELECT * FROM armigers_e WHERE discord_id == ?;", (ctx.author.id,)
		)
		
		if not user:
			await self.bot.get_cog("Bot tasks").sync_book()
		
			user = await ctx.bot.dbc.execute_fetchone(
				"SELECT * FROM armigers_e WHERE discord_id == ?;", (ctx.author.id,)
			)
			
		if user: return user
		
		raise utils.CustomCommandError(
			"Invalid armiger",
			"There are no arms associated with your user account. "
			"To find those of another user, follow the command with their username."
			"If you wish to register your arms, follow the instructions at the Roll of Arms server."
		)
	
	@staticmethod
	def format_armiger(user):
		return user[2] if user[3] == -1 else f"{user[2]}#{user[3]:04}"

async def setup(bot):
	await bot.add_cog(HeraldryRoll(bot))
