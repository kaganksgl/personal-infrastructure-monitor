from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


# Unknown fields are ignored (not rejected) so a newer agent can talk to an
# older server; anything that *is* declared is type- and range-checked.
class WireModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


Percent = Annotated[float, Field(ge=0, le=100)]
NonNegFloat = Annotated[float, Field(ge=0)]
NonNegInt = Annotated[int, Field(ge=0)]
Counter = Annotated[int, Field(ge=0, le=2**64)]
ShortStr = Annotated[str, Field(max_length=64)]
MediumStr = Annotated[str, Field(max_length=256)]

AGENT_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]{1,62}$"
AgentId = Annotated[str, Field(pattern=AGENT_ID_PATTERN)]
