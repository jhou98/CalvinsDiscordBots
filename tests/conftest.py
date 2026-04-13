"""
Shared fixtures for Discord bot tests.
Provides mock Discord objects so tests run without a live bot.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest


@pytest.fixture
def mock_user():
    """A fake discord.Member with a stable ID and mention string."""
    user = MagicMock(spec=discord.Member)
    user.id = "123456789"
    user.mention = "<@123456789>"
    return user


@pytest.fixture
def mock_message():
    """A fake discord.Message with an async edit method."""
    message = MagicMock(spec=discord.Message)
    message.edit = AsyncMock()
    return message


@pytest.fixture
def mock_interaction(mock_user, mock_message):
    """A fake discord.Interaction wired up with common async methods."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = mock_user
    interaction.channel_id = "222"
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.original_response = AsyncMock(return_value=mock_message)
    return interaction


def make_interaction(user_id="123456789", channel_id="222"):
    """Factory for mock interactions with custom user/channel IDs."""
    mock_message = MagicMock(spec=discord.Message)
    mock_message.edit = AsyncMock()
    user = MagicMock(spec=discord.Member)
    user.id = user_id
    user.mention = f"<@{user_id}>"
    user.display_name = "TestUser"
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = user
    interaction.channel_id = channel_id
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.original_response = AsyncMock(return_value=mock_message)
    interaction.message = mock_message
    return interaction, mock_message
