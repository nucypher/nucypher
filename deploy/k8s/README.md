
## k8s dev flow
#### 1. install minikube

then:
*  `minikube config set memory 3000`
*  `minikube start`
*  `kubectl create secret generic nucypher-keyring-password --from-literal=keyring-password='<PASSWORD>' #16 chars`

If you want to have the ursula push its config to S3:

* export AWS_ACCESS_KEY_ID=<aws profile id>
* export AWS_SECRET_ACCESS_KEY=<aws profile secret>



*  `kubectl create secret generic nucypher-aws --from-literal=bucket-name=<AN S3 BUCKET>`
*  `kubectl create secret generic nucypher-aws-secrets --from-literal=aws-secret-access-key=$AWS_SECRET_ACCESS_KEY --from-literal=aws-access-key-id=$AWS_ACCESS_KEY_ID`

these can be each be done in a separate shell

*  `eval $(minikube docker-env)`
*  `docker build . -t nucypher:local --file deploy/docker/Dockerfile #this is only while we are doing live dev.`
*  `docker build ./deploy/k8s -t nucypher:geth --file deploy/k8s/GethDockerfile`


then when those are done

* `kubectl apply -f deploy/k8s/ursula_pod.yml`

then the dashboard:
`minikube dashboard`
