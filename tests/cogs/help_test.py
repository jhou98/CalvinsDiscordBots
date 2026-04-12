"""
Tests for cogs/help.py — the /help command.
"""

import pytest

from src.cogs.help import COMMANDS, Help
from tests.conftest import make_interaction


class TestHelpCommand:
    @pytest.mark.asyncio
    async def test_sends_ephemeral_embed(self):
        interaction, _ = make_interaction()
        cog = Help(bot=None)
        await cog.help_command.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs["ephemeral"] is True
        embed = kwargs["embed"]
        assert "Commands" in embed.title
        assert len(embed.fields) == len(COMMANDS)

    @pytest.mark.asyncio
    async def test_embed_lists_all_commands(self):
        interaction, _ = make_interaction()
        cog = Help(bot=None)
        await cog.help_command.callback(cog, interaction)

        embed = interaction.response.send_message.call_args.kwargs["embed"]
        field_text = " ".join(f.name for f in embed.fields)
        for name, _, _ in COMMANDS:
            assert name in field_text
