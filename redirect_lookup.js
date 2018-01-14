'use strict';
var AWS = require('aws-sdk');
var dynamodb = new AWS.DynamoDB();

exports.handler = (event, context, callback) => {
     var regex_exp = /(?:\/)([A-Za-z0-9]+)/g
     var params = {
  Key: {
   "domain": {
     S: event.Records[0].cf.request.headers.host[0].value
    },
   "path": {
     S: regex_exp.exec(event.Records[0].cf.request.uri)[1]
    }
  },
  TableName: lookup_table
 };
 dynamodb.getItem(params, function(err, data) {
   if (err) console.log(err, err.stack);
   else     console.log(data);
   const response = {
    status: '302',
    statusDescription: 'Found',
    headers: {
        location: [{
            key: 'Location',
            value: data.Item.target.S,
        }],
    },
    };
    console.log(`Redirecting host ${event.Records[0].cf.request.headers.host[0].value} to ${response.headers.location[0].value}`);
    callback(null, response);
 });
};