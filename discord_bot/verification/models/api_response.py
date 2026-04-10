"""Pydantic models for verification API responses."""

from pydantic import BaseModel, Field


class VerificationAPIResponse(BaseModel):
    """Response data from the verification API.

    Contains player information extracted from screenshots via OCR,
    including in-game name, level, regiment, faction, shard, and time data.

    Attributes:
        name (str): Player's in-game name.
        level (int): Player's level.
        regiment (str): Player's regiment name.
        faction (str): Player's faction ('colonial' or 'wardens').
        shard (str): Server shard ('ABLE' or 'CHARLIE').
        ingame_time (str): Time shown in screenshot (e.g., "268, 07:41").
        war (int): Current war number.
        current_ingame_time (str): Current in-game time (e.g., "278, 08:34").
    """

    name: str = Field(default="", description="Player's in-game name")
    level: int = Field(default=0, description="Player's level")
    regiment: str = Field(default="", description="Player's regiment name")
    faction: str = Field(default="", description="Player's faction ('colonial' or 'wardens')")
    shard: str = Field(default="", description="Server shard ('ABLE' or 'CHARLIE')")
    ingame_time: str = Field(default="", description="Time shown in screenshot")
    war: int = Field(default=0, description="Current war number")
    current_ingame_time: str = Field(default="", description="Current in-game time")


class VerificationAPIResult(BaseModel):
    """Result wrapper for verification API calls.

    Encapsulates the result of a verification API call, including
    success status, HTTP status code, response data, and error information.

    Attributes:
        success (bool): Whether the API call was successful.
        status_code (int): HTTP status code from the API response.
        response (VerificationAPIResponse | None): Parsed response data if successful.
        error_message (str | None): Error message if the call failed.
    """

    success: bool = Field(description="Whether the API call was successful")
    status_code: int = Field(description="HTTP status code from the API response")
    response: VerificationAPIResponse | None = Field(
        default=None, description="Parsed response data if successful"
    )
    error_message: str | None = Field(default=None, description="Error message if the call failed")
