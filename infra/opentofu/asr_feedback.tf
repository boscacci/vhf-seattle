# Attach these additional permissions only to the existing private operator identity.
# Public edge identities never receive label or training-audio access.
data "aws_iam_policy_document" "asr_feedback" {
  for_each = {
    dev = {
      bucket_arn = aws_s3_bucket.dev_raw_audio.arn
      table_arn  = aws_dynamodb_table.dev_radio_events.arn
    }
    prod = {
      bucket_arn = aws_s3_bucket.raw_audio.arn
      table_arn  = aws_dynamodb_table.radio_events.arn
    }
  }

  statement {
    sid = "PrivateFeedbackRecords"
    actions = [
      "dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query",
      "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:TransactWriteItems",
      "dynamodb:ConditionCheckItem"
    ]
    resources = [each.value.table_arn]
    condition {
      test     = "ForAllValues:StringLike"
      variable = "dynamodb:LeadingKeys"
      values   = ["asr#*"]
    }
  }
  statement {
    sid       = "ReadOriginalAndReviewedAudio"
    actions   = ["s3:GetObject"]
    resources = ["${each.value.bucket_arn}/raw/*", "${each.value.bucket_arn}/asr-feedback/audio/*"]
  }
  statement {
    sid       = "ArchiveReviewedAudio"
    actions   = ["s3:PutObject", "s3:PutObjectTagging"]
    resources = ["${each.value.bucket_arn}/asr-feedback/audio/*"]
  }
  statement {
    sid       = "BoundReviewedAudioStorage"
    actions   = ["s3:ListBucket"]
    resources = [each.value.bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["asr-feedback/audio/*"]
    }
  }
}
