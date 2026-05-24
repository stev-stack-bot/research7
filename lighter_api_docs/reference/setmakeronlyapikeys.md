# setMakerOnlyApiKeys

Set maker-only API key indexes. This replaces the current list; pass all indexes you want marked as maker-only. Pass [] to clear all maker-only restrictions.

# OpenAPI definition

```json
{
  "openapi": "3.0.0",
  "info": {
    "title": "",
    "version": ""
  },
  "paths": {
    "/api/v1/setMakerOnlyApiKeys": {
      "post": {
        "summary": "setMakerOnlyApiKeys",
        "operationId": "setMakerOnlyApiKeys",
        "tags": [
          "account"
        ],
        "description": "Set maker-only API key indexes. This replaces the current list; pass all indexes you want marked as maker-only. Pass [] to clear all maker-only restrictions.",
        "parameters": [
          {
            "name": "authorization",
            "in": "header",
            "required": true,
            "schema": {
              "type": "string"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/x-www-form-urlencoded": {
              "schema": {
                "$ref": "#/components/schemas/ReqSetMakerOnlyApiKeys"
              }
            },
            "multipart/form-data": {
              "schema": {
                "$ref": "#/components/schemas/ReqSetMakerOnlyApiKeys"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "A successful response.",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/RespSetMakerOnlyApiKeys"
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
      "ReqSetMakerOnlyApiKeys": {
        "type": "object",
        "title": "ReqSetMakerOnlyApiKeys",
        "description": "Send as form data, not JSON. The value replaces the full maker-only API key list; use [] to clear all restrictions.",
        "properties": {
          "account_index": {
            "type": "integer",
            "format": "int64"
          },
          "api_key_indexes": {
            "type": "string",
            "description": "JSON array string of API key indexes, e.g. \"[4,5]\". Use [] to clear all maker-only restrictions."
          },
          "auth": {
            "type": "string"
          }
        },
        "required": [
          "account_index",
          "api_key_indexes"
        ]
      },
      "RespSetMakerOnlyApiKeys": {
        "type": "object",
        "title": "RespSetMakerOnlyApiKeys",
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
        "required": [
          "code"
        ]
      },
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
      }
    }
  }
}
```