resource "aws_dynamodb_table" "scores" {
  name         = "mediguess-scores"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "player_id"
  range_key    = "played_at"

  attribute {
    name = "player_id"
    type = "S"
  }
  attribute {
    name = "played_at"
    type = "S"
  }
  attribute {
    name = "board"
    type = "S"
  }
  attribute {
    name = "score"
    type = "N"
  }

  global_secondary_index {
    name            = "by_score"
    hash_key        = "board"
    range_key       = "score"
    projection_type = "ALL"
  }
}

output "scores_table_name" {
  value = aws_dynamodb_table.scores.name
}
