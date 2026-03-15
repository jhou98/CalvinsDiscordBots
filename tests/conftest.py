"""
Shared fixtures for Discord bot tests.
Provides mock Discord objects so tests run without a live bot.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import discord

@pytest.fixture
def mock_user():
    """A fake discord.Member with a stable ID and mention string."""
    user = MagicMock(spec=discord.Member)
    user.id = 123456789
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
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.original_response = AsyncMock(return_value=mock_message)
    return interaction