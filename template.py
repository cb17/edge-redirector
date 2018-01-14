from troposphere import Sub, GetAtt, Join, If, Not, Equals
from troposphere import Parameter, Ref, Template
from troposphere.route53 import RecordSetType
from troposphere.cloudfront import Distribution, DistributionConfig
from troposphere.cloudfront import Origin, DefaultCacheBehavior, ForwardedValues, LambdaFunctionAssociation, CustomOrigin
from troposphere.dynamodb import (KeySchema, AttributeDefinition,
                                  ProvisionedThroughput)
from troposphere.dynamodb import Table
from troposphere.iam import Role, Policy
from troposphere.awslambda import Function, Code, Version
import hashlib

no_value = Ref("AWS::NoValue")

t = Template()

t.add_description("Custom URL Redirect Endpoint that runs at the edge leveraging CloudFront, Lambda, and Dynamo")

hosted_zone = t.add_parameter(Parameter(
    "HostedZone",
    Description="The DNS name of an existing Amazon Route 53 hosted zone",
    Type="String",
))

additional_cname_1 = t.add_parameter(Parameter(
    "AdditionalCNAME1",
    Description="Additional CNAME for CF Distribution",
    Type="String",
    Default="None"
))

additional_cname_2 = t.add_parameter(Parameter(
    "AdditionalCNAME2",
    Description="Additional CNAME for CF Distribution",
    Type="String",
    Default="None"
))

t.add_condition(
    "AdditionalCNAME1Check",
    Not(Equals(Ref(additional_cname_1), "None")))

additional_cname_2_check = t.add_condition(
    "AdditionalCNAME2Check",
    Not(Equals(Ref(additional_cname_2), "None")))

read_units = t.add_parameter(Parameter(
    "ReadCapacityUnits",
    Description="Provisioned read throughput",
    Type="Number",
    Default="1",
    MinValue="1",
    MaxValue="10000",
    ConstraintDescription="should be between 5 and 10000"
))

write_units = t.add_parameter(Parameter(
    "WriteCapacityUnits",
    Description="Provisioned write throughput",
    Type="Number",
    Default="1",
    MinValue="1",
    MaxValue="10000",
    ConstraintDescription="should be between 5 and 10000"
))

redirect_lookup_table = t.add_resource(Table(
    "RedirectLookupTable",
    AttributeDefinitions=[
        AttributeDefinition(
            AttributeName="domain",
            AttributeType="S"
        ),
        AttributeDefinition(
            AttributeName="path",
            AttributeType="S"
        )
    ],
    KeySchema=[
        KeySchema(
            AttributeName="domain",
            KeyType="HASH"
        ),
        KeySchema(
            AttributeName="path",
            KeyType="RANGE"
        )
    ],
    ProvisionedThroughput=ProvisionedThroughput(
        ReadCapacityUnits=Ref(read_units),
        WriteCapacityUnits=Ref(write_units)
    )
))

edge_lambda_execution_role = t.add_resource(Role(
    "EdgeLambdaExecutionRole",
    Path="/",
    Policies=[Policy(
        PolicyName="root",
        PolicyDocument={
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": ["logs:*"],
                    "Resource": "arn:aws:logs:*:*:*",
                    "Effect": "Allow"
                },
                {
                    "Action": ["dynamodb:GetItem"],
                    "Resource": GetAtt(redirect_lookup_table, "Arn"),
                    "Effect": "Allow"
                }
            ]
        })],
    AssumeRolePolicyDocument={
        "Version": "2012-10-17",
        "Statement": [{
            "Action": ["sts:AssumeRole"],
            "Effect": "Allow",
            "Principal": {
                "Service": [
                  "edgelambda.amazonaws.com",
                  "lambda.amazonaws.com"
                ],
            }
        }]
    },
))

lambda_redirect_lookup = t.add_resource(Function(
    "RedirectLookup",
    Code=Code(
        ZipFile=Join("", ["var lookup_table = \"", Ref(redirect_lookup_table), "\";\n"] + open("redirect_lookup.js").readlines())
    ),
    Handler="index.handler",
    Role=GetAtt(edge_lambda_execution_role, "Arn"),
    Runtime="nodejs6.10",
    MemorySize=128,
    Timeout="5"
))

function_code_hash = hashlib.md5(open("redirect_lookup.js").read().encode()).hexdigest()


lambda_redirect_lookup_version = t.add_resource(Version(
    "RedirectLookupLambdaVersion"+function_code_hash,
    FunctionName=Ref(lambda_redirect_lookup)
))

redirect_distribution = t.add_resource(Distribution(
    "RedirectDistribution",
    DistributionConfig=DistributionConfig(
        Aliases=[
            Sub("*.links.${HostedZone}"),
            Sub("links.${HostedZone}"),
            If("AdditionalCNAME1Check", Ref(additional_cname_1), no_value),
            If("AdditionalCNAME2Check", Ref(additional_cname_2), no_value)
        ],
        Origins=[Origin(Id="Default", DomainName="google.com", CustomOriginConfig=CustomOrigin(OriginProtocolPolicy="http-only"))],
        DefaultCacheBehavior=DefaultCacheBehavior(
            TargetOriginId="Default",
            ForwardedValues=ForwardedValues(
                QueryString=False
            ),
            LambdaFunctionAssociations=[
                LambdaFunctionAssociation(
                    EventType= "viewer-request",
                    LambdaFunctionARN= Ref(lambda_redirect_lookup_version)
                )
            ],
            ViewerProtocolPolicy="allow-all"),
        Enabled=True,
        HttpVersion='http2'
    )
))

wildcard_redirect_record = t.add_resource(RecordSetType(
    "WildcardLinksRedirectRecord",
    HostedZoneName=Sub("${HostedZone}."),
    Comment="Wildcard CNAME redirect to CloudFront distribution",
    Name=Sub("*.links.${HostedZone}."),
    Type="CNAME",
    TTL="300",
    ResourceRecords=[GetAtt(redirect_distribution, "DomainName")]
))

redirect_record = t.add_resource(RecordSetType(
    "LinksRedirectRecord",
    HostedZoneName=Sub("${HostedZone}."),
    Comment="CNAME redirect to CloudFront distribution",
    Name=Sub("links.${HostedZone}."),
    Type="CNAME",
    TTL="300",
    ResourceRecords=[GetAtt(redirect_distribution, "DomainName")]
))

additional_cname_1_record = t.add_resource(RecordSetType(
    "AdditionalRedirectRecord1",
    HostedZoneName=Sub("${HostedZone}."),
    Comment="CNAME redirect to CloudFront distribution",
    Name=Sub("${AdditionalCNAME1}."),
    Type="CNAME",
    TTL="300",
    ResourceRecords=[GetAtt(redirect_distribution, "DomainName")],
    Condition="AdditionalCNAME1Check"
))

additional_cname_2_record = t.add_resource(RecordSetType(
    "AdditionalRedirectRecord2",
    HostedZoneName=Sub("${HostedZone}."),
    Comment="CNAME redirect to CloudFront distribution",
    Name=Sub("${AdditionalCNAME2}."),
    Type="CNAME",
    TTL="300",
    ResourceRecords=[GetAtt(redirect_distribution, "DomainName")],
    Condition="AdditionalCNAME2Check"
))

print(t.to_json())
