# syntheticSpotInfo

Get synthetic spot info for a symbol. For complete details see: https://docs.lighter.xyz/trading/real-world-assets-rwas/us-equity-indices

# OpenAPI definition

```json
{
  "openapi": "3.0.0",
  "info": {
    "title": "",
    "version": ""
  },
  "paths": {
    "/api/v1/syntheticSpotInfo": {
      "get": {
        "summary": "syntheticSpotInfo",
        "operationId": "syntheticSpotInfo",
        "tags": [
          "info"
        ],
        "description": "Get synthetic spot info for a symbol. For complete details see: https://docs.lighter.xyz/trading/real-world-assets-rwas/us-equity-indices",
        "parameters": [
          {
            "name": "symbol",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "A successful response.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/RespSyntheticSpotInfo"
                }
              }
            }
          },
          "400": {
            "description": "Bad request",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ResultCode"
                }
              }
            }
          }
        }
      }
    }
  },
  "servers": [
    {
      "url": "https://mainnet.zklighter.elliot.ai"
    }
  ],
  "components": {
    "schemas": {
      "ResultCode": {
        "type": "object",
        "properties": {
          "code": {
            "type": "integer",
            "format": "int32",
            "example": "200"
          },
          "message": {
            "type": "string"
          }
        },
        "title": "ResultCode",
        "required": [
          "code"
        ]
      },
      "RespSyntheticSpotInfo": {
        "type": "object",
        "properties": {
          "code": {
            "type": "integer",
            "format": "int32",
            "example": "200"
          },
          "message": {
            "type": "string"
          },
          "bps_per_day": {
            "type": "number",
            "format": "double"
          },
          "expiry_time_ms": {
            "type": "integer",
            "format": "int64"
          },
          "spot_close_ms": {
            "type": "integer",
            "format": "int64"
          },
          "source": {
            "type": "string"
          },
          "symbol": {
            "type": "string"
          }
        },
        "title": "RespSyntheticSpotInfo",
        "required": [
          "code",
          "bps_per_day",
          "expiry_time_ms",
          "spot_close_ms",
          "source",
          "symbol"
        ]
      }
    }
  }
}
```