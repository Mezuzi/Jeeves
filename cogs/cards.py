import discord
from discord.ext import commands
from markdownify import markdownify as md
import requests
from fuzzywuzzy import fuzz

import re
import unicodedata
import configparser
from typing import List, Dict

class CardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.cards = dict()
        self.cycles = dict()
        self.packs = dict()
        self.mwl = dict()

        # Emojis thanks to user qwitwa#9367 on Discord!
        self.emojis = {
            'interrupt': '<:gninterrupt:854706842835615764>',
            'agenda': '<:gnagenda:854706842814251008>',
            'click': '<:gnclick:854706842869432330>',
            'credit': '<:gncredit:854716895966265346>',
            'mu': '<:gnmu:854706842873757776>',
            'recurring-credit': '<:gnrecurring:854706842840203295>',
            'rez': '<:gnrez:854706842642677822>',
            'trash': '<:gntrashability:854706842905870396>', # TODO - Use both trash and trash cost emojis.
            'subroutine': '↳',
            'link': ' <:gnlink:854706842957512734>', # Yes, there is a space here - the emoji looks *terrible* without it.
            'weyland-consortium': '<:nrweyland:744275191714152548>',
            'jinteki': '<:nrjinteki:744275192074993734>',
            'haas-bioroid': '<:nrhaasbioroid:744275192142102600>',
            'nbn': '<:nrnbn:744275191856758891>',
            'anarch': '<:nranarch:744275191433134135>',
            'shaper': '<:nrshaper:744275192028856430>',
            'criminal': '<:nrcriminal:744275191974330440>',
            'apex': '<:nrapex:744275777842970716>',
            'adam': '<:nradam:744275777926856755>',
            'sunny-lebeau': '<:nrsunny:744275778073788536>'
        }

        self.config = configparser.ConfigParser()

        self.load_cards()
        self.load_config()

    def load_config(self):
        self.config.read('cards.ini')

    def load_cards(self):
        # TODO - Marshel these cards into type-safe classes.
        card_data = requests.get('https://netrunnerdb.com/api/2.0/public/cards').json()['data']

        # TODO - Marshel these cycles into type-safe classes.
        cycle_data = requests.get('https://netrunnerdb.com/api/2.0/public/cycles').json()['data']

        # TODO - Marshel these packs into type-safe classes.
        pack_data = requests.get('https://netrunnerdb.com/api/2.0/public/packs').json()['data']

        # TODO - Marshel the ban-list into type-safe classes.
        # Also make it so it elegantly handles the different MWL cases.
        mwl_data = requests.get('https://netrunnerdb.com/api/2.0/public/mwl').json()['data'][-1]

        # Since card-lookup by name is the most common, re-key the array into dict w/ names as keys. 
        # Also has a side-benefit of pulling only the most-recent version of a card in case of re-prints.
        self.cards = { self.strip_accents(x['title']): x for x in card_data }

        self.cycles = { x['code']: x for x in cycle_data }
        self.packs = { x['code']: x for x in pack_data }
        self.mwl = mwl_data

    def strip_accents(self, text) -> str:
        return ''.join(c for c in unicodedata.normalize('NFKD', text) if unicodedata.category(c) != 'Mn').lower()

    def score_card(self, text, card_title) -> int:
        if self.config.has_option('Aliases', text) and self.strip_accents(self.config.get('Aliases', text)) == card_title:
            return 300
        elif text == card_title:
            return 200
        else:
            return fuzz.ratio(text, card_title) + (70 if text in card_title else 0)

    def search_card(self, text) -> str:
        return max([*self.cards.keys()], key=lambda x: self.score_card(text, x))

    def clean_card_text(self, text: str) -> (str, str):
        emoji_text = text
        for e, e_code in self.emojis.items():
            emoji_text = emoji_text.replace(f'[{e}]', e_code)

        # Note - as Discord only supports a subset of markdown, we will need to handle list formatting ourselves.
        emoji_text = emoji_text.replace(f'<ul>', '\n')
        emoji_text = emoji_text.replace(f'<li>', '• ')
        emoji_text = emoji_text.replace(f'</li>', '\n')

        emoji_text = discord.utils.escape_markdown(emoji_text)

        lines = emoji_text.splitlines()
        return ('\n'.join(['' if t.startswith('<errata>') else md(t) for t in lines]), md(lines[-1]) if len(lines) > 0 and lines[-1].startswith('<errata>') else '')

    def generate_header_for_card(self, card) -> (str, str):
        # In order of appending:
        # Agenda Cost, Agenda Points, (Cost/Rez), Strength, Trash, Link, Influence Count, Influence Cost

        f_cost = None
        if 'type_code' in card and card['type_code'] != 'identity' and card['type_code'] != 'agenda':
            rez_costs = ['asset', 'ice', 'upgrade']        
            has_cost_play = f"{self.emojis['credit']}" if card['type_code'] not in rez_costs else None
            has_cost_rez = f"{self.emojis['credit']}" if card['type_code'] in rez_costs else None
            f_emoji = ""
            if has_cost_play:
                f_emoji = has_cost_play
            elif has_cost_rez:
                f_emoji = has_cost_rez
                
            f_cost = f"""{card['cost'] if 'cost' in card 
                and card['cost'] is not None 
                and card['cost'] != 'None' 
                else "X"}{f_emoji}"""

        headers = [
            f"""{f"{card['advancement_cost']}{self.emojis['rez']}" if 'advancement_cost' in card else ""}""",
            f"""{f"{card['agenda_points']}{self.emojis['agenda']}" if 'agenda_points' in card else ""}""",
            f_cost,
            f"""{f"{card['memory_cost']}{self.emojis['mu']}" if 'memory_cost' in card else ""}""", # 
            f"""{f"{card['strength']} Strength" if 'strength' in card else ""}""",
            f"""{f"{card['trash_cost']}{self.emojis['trash']}" if 'trash_cost' in card else ""}""",
            f"""{f"{card['base_link']}{self.emojis['link']}" if 'base_link' in card else ""}""",
            f"""{
                f"{(card['minimum_deck_size'] if card['minimum_deck_size'] else '∞')} / {(card['influence_limit'] if card['influence_limit'] else '∞')}" 
                if 'influence_limit' in card and 'minimum_deck_size' in card else ""}"""
        ]
        return (', '.join(filter(None, headers)), f" {'●'*card['faction_cost']}{'○'*(5-card['faction_cost'])}"
            if ('faction_cost' in card and 'type_code' in card and 'faction_code' in card
                and (card['type_code'] != 'identity' and 
                    (card['type_code'] != 'agenda' or (card['type_code'] == 'agenda' and card['faction_code'] == 'neutral-corp'))
            ))
            else '')

    def generate_color_for_faction(self, faction: str) -> discord.Color:
        if faction == 'weyland-consortium':
            return discord.Color.dark_teal()
        elif faction == 'nbn':
            return discord.Color.gold()
        elif faction == 'jinteki':
            return discord.Color.dark_red()
        elif faction == 'haas-bioroid':
            return discord.Color.purple()
        elif faction == 'anarch':
            return discord.Color.dark_orange()
        elif faction == 'criminal':
            return discord.Color.blue()
        elif faction == 'shaper':
            return discord.Color.green()
        elif faction == 'adam':
            # Brown seems fine, but going for more of a 'tan' look.
            return discord.Color.from_rgb(210, 180, 140)
        elif faction == 'sunny-lebeau':
            return discord.Color.from_rgb(66, 66, 66)
        elif faction == 'apex':
            # _Really_ dark red.
            return discord.Color.from_rgb(31, 0, 0)
        elif faction == 'neutral-corp':
            return discord.Color.from_rgb(121, 125, 127)
        elif faction == 'neutral-runner':
            return discord.Color.from_rgb(15, 156, 159)
        else:
            # I DUNNO, WE SHOULDN'T BE HERE BUT WE NEED A COLOR. New mini-factions NISEI plz?
            return discord.Color.default()

    # TODO - Get some faction symbols on here!
    def generate_symbol_for_faction(self, faction: str) -> str:
        return ''

    # TODO - Get some cycle symbols on here!
    def generate_cycle_symbol_for_cycle(self, cycle: str) -> str:
        return ''

    def generate_embed(self, card) -> discord.Embed:
        # A Discord embed is made up of several parts:
        # The 'title', where we will put the card name and uniqueness flag at.
        title = f"{'◆ ' if card['uniqueness'] else ''}{card['title']}"

        # The 'url', where we will put a link to the NRDB card.
        url = f"https://netrunnerdb.com/en/card/{card['code']}"

        # The 'description', where we will put the text of the card in. Note that text comming from NRDB
        # uses HTML tags for some reason, which looks ugly in Discord, so convert to Markdown first.
        card_type = 'ICE' if card['type_code'] == 'ice' else card['type_code'].title()
        card_keywords = f": {card['keywords']}" if 'keywords' in card else ''
        (card_subtypes, influence) = self.generate_header_for_card(card)
        card_attributes = f"**{card_type}{card_keywords}** ({card_subtypes}){influence}"
        (card_body, errata) = self.clean_card_text(card.get('text', ""))

        text = f"{card_attributes}\n{card_body}"

        # The 'color', where we do some touch-up and make the side-bar pretty.
        color = self.generate_color_for_faction(card['faction_code'])

        embed = discord.Embed(title=title, description=text, url=f"https://netrunnerdb.com/en/card/{card['code']}", color=color)

        # The 'footer', where we will put the faction symbol, pack, cycle, card position, etc.
        pack_data = self.packs[card['pack_code']]
        cycle_data = self.cycles[pack_data['cycle_code']]

        pack_info = '' if cycle_data['size'] == 1 else pack_data['name']
        cycle_info = f"{cycle_data['name']} #{card['position']}{' (Rotated)' if cycle_data['rotated'] else ''}"
        misc_info = '\n'.join(
        [f"""{card['faction_code'].replace('-', ' ').upper() if card['faction_code'] == 'nbn' else card['faction_code'].replace('-', ' ').title()} {f'/ {pack_info} ' if pack_info else ''}/ {cycle_info}{f' - {errata}' if errata else ''}""",
        (f"{self.mwl['name']} - Banned" if card['code'] in self.mwl['cards'] else "")])

        embed.set_footer(text=misc_info)

        # The 'thumbnail', where we will put the card image in.
        embed.set_thumbnail(url=f"https://netrunnerdb.com/card_image/large/{card['code']}.jpg")

        return embed

    def generate_image(self, card) -> discord.Embed:
        title = f"{'◆ ' if card['uniqueness'] else ''}{card['title']}"
        color = self.generate_color_for_faction(card['faction_code'])
        embed = discord.Embed(title=title, url=f"https://netrunnerdb.com/en/card/{card['code']}", color=color)
        embed.set_image(url=f"https://netrunnerdb.com/card_image/large/{card['code']}.jpg")
        return embed

    def generate_flavor(self, card) -> discord.Embed:
        title = f"{'◆ ' if card['uniqueness'] else ''}{card['title']}"
        color = self.generate_color_for_faction(card['faction_code'])
        flavor = "*No flavor text.*"
        if 'flavor' in card:
            (txt, e) = self.clean_card_text(card['flavor'])
            flavor = f"*{txt}*"

        # let maxx swear!
        if card['title'] == "MaxX: Maximum Punk Rock":
            flavor = "*Fuck you, motherfucker!*"

        embed = discord.Embed(description=flavor, color=color)
        embed.set_author(name=title, url=f"https://netrunnerdb.com/en/card/{card['code']}", icon_url=f"https://netrunnerdb.com/card_image/small/{card['code']}.jpg")
        return embed


    @commands.command(name='trans_agenda')
    async def trans_agenda(self, message):
        await message.channel.send('https://cdn.discordapp.com/attachments/732385125039472692/866103176067547156/the_trans_agenda.png')
    @commands.command(name='holy_hell')
    async def holy_hell(self, message):
        await message.channel.send('https://cdn.discordapp.com/attachments/732385125039472692/868392291696533504/holy_hell.png')
    @commands.command(name='timing')
    async def timing(self, message):
        await message.channel.send('https://cdn.discordapp.com/attachments/653990064207953921/837916163149135882/rulesRUNNNNNNN.png')

    @commands.command(name='force_reload', hidden=True)
    @commands.check_any(commands.is_owner())
    async def force_reload(self, ctx):
        self.load_cards()
        await ctx.send(f"Very good sir, I've loaded {len(self.cards)} cards into memory now.")

    @commands.Cog.listener()
    async def on_message(self, message):
        embed_results = re.findall('\[\[(.*?)\]\]', message.content)
        image_results = re.findall('\{\{(.*?)\}\}', message.content)
        flavor_results = re.findall('<<(.*?)>>', message.content)

        if len(embed_results) > 0:
            queries = [ self.search_card(self.strip_accents(q)) for q in embed_results[:self.config.getint('Configuration', 'MaxSearches')] ]
            embeds = [ self.generate_embed(self.cards[c]) for c in queries ]
            for e in embeds:
                await message.channel.send(embed=e)

        elif len(image_results) > 0:
            queries = [ self.search_card(self.strip_accents(q)) for q in image_results[:self.config.getint('Configuration', 'MaxSearches')] ]
            urls = [ self.generate_image(self.cards[c]) for c in queries ]
            for u in urls:
                await message.channel.send(embed=u)

        elif len(flavor_results) > 0:
            queries = [ self.search_card(self.strip_accents(q)) for q in flavor_results[:self.config.getint('Configuration', 'MaxSearches')] ]
            flavors = [ self.generate_flavor(self.cards[c]) for c in queries ]
            for f in flavors:
                await message.channel.send(embed=f)

def setup(bot):
    bot.add_cog(CardCog(bot))