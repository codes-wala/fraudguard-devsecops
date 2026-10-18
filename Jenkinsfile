// FraudGuard CI/CD pipeline: build, test, scan, containerise, deploy.
pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 40, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    parameters {
        booleanParam(name: 'QUALITY_GATE',     defaultValue: false, description: 'Fail the build if the SonarQube quality gate fails')
        booleanParam(name: 'FAIL_ON_CRITICAL', defaultValue: false, description: 'Fail the build if Trivy finds CRITICAL vulnerabilities in the image')
        booleanParam(name: 'PUSH_IMAGE',       defaultValue: false, description: 'Push the image to Docker Hub (needs the dockerhub-creds credential)')
        string(name: 'DOCKERHUB_USER',         defaultValue: 'your-dockerhub-username', description: 'Docker Hub user name')
    }

    environment {
        APP_NAME   = 'fraudguard'
        IMAGE_TAG  = "${env.BUILD_NUMBER}"
        SONAR_HOST = 'http://sonarqube:9000'
        DOCKER_NET = 'devsecops'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                sh 'mkdir -p reports'
            }
        }

        stage('Install and Unit Tests') {
            steps {
                sh '''
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install -r requirements-dev.txt
                    coverage run -m pytest -q --junitxml=reports/junit.xml
                    coverage xml -o coverage.xml
                    coverage report
                '''
            }
            post {
                always { junit allowEmptyResults: true, testResults: 'reports/junit.xml' }
            }
        }

        stage('SAST - Bandit') {
            steps {
                sh '''
                    . .venv/bin/activate
                    bandit -r fraud_detector -f json -o reports/bandit.json || true
                    bandit -r fraud_detector || true
                '''
            }
        }

        stage('Dependency Audit - pip-audit') {
            steps {
                sh '''
                    . .venv/bin/activate
                    pip-audit -r requirements.txt -f json -o reports/pip-audit.json || true
                    pip-audit -r requirements.txt || true
                '''
            }
        }

        stage('SonarQube Analysis') {
            steps {
                withCredentials([string(credentialsId: 'sonar-token', variable: 'SONAR_TOKEN')]) {
                    sh '''
                        docker run --rm --network ${DOCKER_NET} --volumes-from jenkins -w "$WORKSPACE" \
                          -e SONAR_HOST_URL=${SONAR_HOST} -e SONAR_TOKEN="$SONAR_TOKEN" \
                          sonarsource/sonar-scanner-cli \
                          -Dsonar.qualitygate.wait=${QUALITY_GATE}
                    '''
                }
            }
        }

        stage('Trivy - Dependencies and Config') {
            steps {
                sh '''
                    docker run --rm --volumes-from jenkins -w "$WORKSPACE" -v trivy-cache:/root/.cache aquasec/trivy:latest \
                      fs --scanners vuln,secret,misconfig --format json -o reports/trivy-fs.json .
                    docker run --rm --volumes-from jenkins -w "$WORKSPACE" -v trivy-cache:/root/.cache aquasec/trivy:latest \
                      fs --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --format table .
                '''
            }
        }

        stage('Docker Build') {
            steps {
                sh 'docker build -t ${APP_NAME}:${IMAGE_TAG} -t ${APP_NAME}:latest .'
            }
        }

        stage('Trivy - Image Scan') {
            steps {
                sh '''
                    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache aquasec/trivy:latest \
                      image --format json ${APP_NAME}:${IMAGE_TAG} > reports/trivy-image.json
                    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache aquasec/trivy:latest \
                      image --severity HIGH,CRITICAL --format table ${APP_NAME}:${IMAGE_TAG}
                '''
                script {
                    if (params.FAIL_ON_CRITICAL) {
                        sh '''
                            docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache aquasec/trivy:latest \
                              image --exit-code 1 --severity CRITICAL --ignore-unfixed ${APP_NAME}:${IMAGE_TAG}
                        '''
                    }
                }
            }
        }

        stage('Push Image') {
            when { expression { return params.PUSH_IMAGE } }
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub-creds', usernameVariable: 'DH_USER', passwordVariable: 'DH_PASS')]) {
                    sh '''
                        echo "$DH_PASS" | docker login -u "$DH_USER" --password-stdin
                        docker tag ${APP_NAME}:${IMAGE_TAG} ${DOCKERHUB_USER}/${APP_NAME}:${IMAGE_TAG}
                        docker tag ${APP_NAME}:${IMAGE_TAG} ${DOCKERHUB_USER}/${APP_NAME}:latest
                        docker push ${DOCKERHUB_USER}/${APP_NAME}:${IMAGE_TAG}
                        docker push ${DOCKERHUB_USER}/${APP_NAME}:latest
                        docker logout
                    '''
                }
            }
        }

        stage('Deploy with Docker') {
            steps {
                sh '''
                    docker rm -f ${APP_NAME} || true
                    docker run -d --name ${APP_NAME} --restart unless-stopped -p 5000:5000 ${APP_NAME}:${IMAGE_TAG}
                    sleep 8
                    docker exec ${APP_NAME} python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:5000/api/health').read().decode())"
                '''
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'reports/**, coverage.xml', allowEmptyArchive: true
        }
        success { echo 'Pipeline finished. Website: http://localhost:5000' }
        failure { echo 'Pipeline failed. Check the stage logs above.' }
    }
}
