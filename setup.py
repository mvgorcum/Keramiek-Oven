from setuptools import find_packages, setup

setup(
    name='oven_control',
    version='1.0.0',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'flask',
        'RPi.GPIO',
        'signal',
        'sys',
        'threading',
        'json',
        'types',
    ],
)

 
